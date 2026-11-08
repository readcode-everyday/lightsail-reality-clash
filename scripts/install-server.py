#!/usr/bin/env python3
"""Install a dedicated Xray REALITY service on a Linux systemd host."""

import argparse
import datetime
import grp
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import pwd
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import urllib.request
import uuid
import zipfile

VERSION = "26.10.31"
SERVICE = "lightsail-reality-clash"
CONFIG = Path("/etc") / SERVICE / "config.json"
STATE = Path("/var/lib") / SERVICE
BINARY = Path("/usr/local/lib") / SERVICE / "xray"
UNIT = Path("/etc/systemd/system") / (SERVICE + ".service")


def validate_host(value):
    try:
        ipaddress.ip_address(value)
        return value
    except ValueError:
        if len(value) > 253 or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
            raise argparse.ArgumentTypeError("Use an IP address or hostname, without a URL or port")
        if any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
               for label in value.split('.')):
            raise argparse.ArgumentTypeError("Invalid hostname")
        return value


def checksum_matches(data, published):
    return hashlib.sha256(data).hexdigest() in re.findall(r"\b[0-9a-f]{64}\b", published.lower())


def parse_keys(output):
    fields = {}
    for line in output.splitlines():
        if ':' in line:
            name, value = line.split(':', 1)
            fields[re.sub(r"[^a-z]", "", name.lower())] = value.strip()
    private = next((v for k, v in fields.items() if k.startswith('privatekey')), None)
    public = next((v for k, v in fields.items() if k.startswith(('password', 'publickey'))), None)
    if not private or not public:
        raise ValueError("Xray key generation returned an unsupported format")
    return private, public


def build_configs(server, target, port, name, private_key, public_key, client_id, short_id):
    server_config = {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "tag": "reality-in", "listen": "0.0.0.0", "port": port, "protocol": "vless",
            "settings": {"clients": [{"id": client_id, "flow": "xtls-rprx-vision"}], "decryption": "none"},
            "streamSettings": {"network": "raw", "security": "reality", "realitySettings": {
                "show": False, "target": target + ":443", "xver": 0,
                "serverNames": [target], "privateKey": private_key, "shortIds": [short_id]
            }}
        }],
        "outbounds": [{"tag": "direct", "protocol": "freedom", "settings": {},
                       "streamSettings": {"sockopt": {"domainStrategy": "UseIPv4"}}}]
    }
    client = {
        "name": name, "type": "vless", "server": server, "port": port,
        "uuid": client_id, "flow": "xtls-rprx-vision", "tls": True, "servername": target,
        "client-fingerprint": "chrome", "udp": True, "packet-encoding": "xudp",
        "reality-opts": {"public-key": public_key, "short-id": short_id,
                         "support-x25519mlkem768": True}
    }
    return server_config, client


def private_write(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": SERVICE})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server', required=True, type=validate_host, help='Public server IPv4 address or hostname')
    parser.add_argument('--target', default='www.cloudflare.com', type=validate_host, help='REALITY handshake target hostname')
    parser.add_argument('--version', default=VERSION, help='Pinned Xray release version')
    parser.add_argument('--port', type=int, default=443)
    parser.add_argument('--name', default='Reality')
    parser.add_argument('--replace', action='store_true', help='Back up and replace this project installation; rotates credentials')
    parser.add_argument('--dry-run', action='store_true', help='Show paths and planned settings without network calls or writes')
    args = parser.parse_args()
    version = args.version.removeprefix('v')
    if not re.fullmatch(r'\d{1,2}\.\d{1,2}\.\d{1,2}', version) or not 1 <= args.port <= 65535:
        parser.error('Invalid release version or port')
    if not args.name.strip():
        parser.error('Node name cannot be empty')
    plan = {"version": version, "server": args.server, "port": args.port, "target": args.target,
            "service": SERVICE, "config": str(CONFIG), "client_output": str(STATE / 'client.json')}
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return
    if platform.system() != 'Linux' or os.geteuid() != 0 or not shutil.which('systemctl'):
        parser.error('Run with sudo on a Linux systemd host')
    if (CONFIG.exists() or UNIT.exists() or (STATE / 'client.json').exists()) and not args.replace:
        parser.error('Project installation already exists; --replace backs it up and rotates credentials')
    arch = {'x86_64': '64', 'aarch64': 'arm64-v8a'}.get(platform.machine())
    if not arch:
        parser.error('Supported server architectures: x86_64 and aarch64')

    # Verify a normal TLS 1.3 / HTTP2 handshake before installing anything.
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.set_alpn_protocols(['h2'])
    with socket.create_connection((args.target, 443), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=args.target) as connection:
            if connection.selected_alpn_protocol() != 'h2':
                raise RuntimeError('Handshake target did not negotiate HTTP/2')
    if not UNIT.exists():
        with socket.socket() as probe:
            probe.bind(('0.0.0.0', args.port))
    asset = 'Xray-linux-' + arch + '.zip'
    release = 'https://github.com/XTLS/Xray-core/releases/download/v' + version + '/'
    archive = download(release + asset)
    published = download(release + asset + '.dgst').decode()
    if not checksum_matches(archive, published):
        raise RuntimeError('Downloaded archive does not match the published SHA256')
    with tempfile.TemporaryFile() as file:
        file.write(archive)
        file.seek(0)
        with zipfile.ZipFile(file) as package:
            binary = package.read('xray')
    STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    STATE.chmod(0o700)
    if args.replace:
        backup = STATE / ('backup-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        backup.mkdir(mode=0o700)
        for path in [BINARY, CONFIG, UNIT, STATE / 'client.json']:
            if path.exists():
                shutil.copy2(path, backup / str(path).strip('/').replace('/', '__'))
    BINARY.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    private_write(BINARY, binary, 0o755)
    private_key, public_key = parse_keys(subprocess.check_output([str(BINARY), 'x25519'], text=True))
    server_config, client = build_configs(args.server, args.target, args.port, args.name,
                                         private_key, public_key, str(uuid.uuid4()), secrets.token_hex(8))
    candidate = STATE / 'config.candidate.json'
    private_write(candidate, (json.dumps(server_config, indent=2) + '\n').encode())
    subprocess.run([str(BINARY), 'run', '-test', '-config', str(candidate)], check=True)
    try:
        pwd.getpwnam(SERVICE)
    except KeyError:
        subprocess.run(['useradd', '--system', '--no-create-home', '--home-dir', str(STATE),
                        '--shell', '/usr/sbin/nologin', SERVICE], check=True)
    group_id = grp.getgrnam(SERVICE).gr_gid
    CONFIG.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(CONFIG.parent, 0, group_id)
    CONFIG.parent.chmod(0o750)
    private_write(CONFIG, candidate.read_bytes(), 0o640)
    os.chown(CONFIG, 0, group_id)
    candidate.unlink()
    private_write(STATE / 'client.json', (json.dumps(client, indent=2) + '\n').encode())
    unit = f'''[Unit]
Description=Lightsail REALITY + Clash node
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={SERVICE}
Group={SERVICE}
ExecStart={BINARY} run -config {CONFIG}
Restart=on-failure
RestartSec=5
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
UMask=0077
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
'''
    private_write(UNIT, unit.encode(), 0o644)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'enable', SERVICE], check=True)
    subprocess.run(['systemctl', 'restart', SERVICE], check=True)
    subprocess.run(['systemctl', 'is-active', '--quiet', SERVICE], check=True)
    print(json.dumps(plan, indent=2))
    print('Installed. Client credentials were saved privately; their values are not printed.')


if __name__ == '__main__':
    main()
