#!/usr/bin/env python3
"""Test a REALITY node with an isolated Mihomo process; never changes the active client."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time


def free_port():
    with socket.socket() as connection:
        connection.bind(('127.0.0.1', 0))
        return connection.getsockname()[1]


def wait_listener(port, process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('Test process exited before becoming ready')
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.2):
                return
        except OSError:
            time.sleep(.1)
    raise TimeoutError('Test listener did not become ready')


def redact(message, node):
    for value in [node.get('uuid'), *node.get('reality-opts', {}).values()]:
        if isinstance(value, str) and value:
            message = message.replace(value, '[redacted]')
    return message


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, type=Path)
    parser.add_argument('--mihomo', default=shutil.which('mihomo'), help='Path to the installed Mihomo binary')
    parser.add_argument('--interface', help='Physical interface, e.g. en0; useful when the active client uses TUN')
    parser.add_argument('--ssh-host', help='Optional SSH alias for diagnosis when public port access is blocked')
    parser.add_argument('--expect-ip')
    parser.add_argument('--expect-country', help='Two-letter exit country code')
    args = parser.parse_args()
    if not args.mihomo or not shutil.which('curl'):
        parser.error('Mihomo and curl are required; specify --mihomo if necessary')
    if args.interface and args.ssh_host:
        parser.error('--interface is for direct tests; do not combine it with --ssh-host')
    node = json.loads(args.client.read_text())
    if node.get('type') != 'vless' or not node.get('reality-opts'):
        parser.error('Expected a generated REALITY client JSON')
    forward = None
    process = None
    results = []
    with tempfile.TemporaryDirectory(prefix='reality-check-') as directory:
        private = Path(directory)
        log = (private / 'core.log').open('w')
        os.chmod(private / 'core.log', 0o600)
        try:
            if args.ssh_host:
                local_port = free_port()
                forward = subprocess.Popen([
                    'ssh', '-N', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'ExitOnForwardFailure=yes', '-o', 'ConnectTimeout=8',
                    '-L', f'127.0.0.1:{local_port}:127.0.0.1:{node["port"]}', '--', args.ssh_host
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                wait_listener(local_port, forward)
                node['server'], node['port'] = '127.0.0.1', local_port
            proxy_port = free_port()
            config = {
                'mixed-port': proxy_port, 'bind-address': '127.0.0.1', 'allow-lan': False,
                'mode': 'rule', 'log-level': 'warning', 'ipv6': False,
                'tun': {'enable': False}, 'profile': {'store-selected': False},
                'proxies': [node], 'rules': ['MATCH,' + node['name']]
            }
            if args.interface:
                config['interface-name'] = args.interface
            config_path = private / 'config.json'
            config_path.write_text(json.dumps(config))
            config_path.chmod(0o600)
            process = subprocess.Popen([args.mihomo, '-d', directory, '-f', str(config_path)],
                                       stdout=log, stderr=subprocess.STDOUT)
            wait_listener(proxy_port, process)
            for name, url, expected in [
                ('exit', 'https://www.cloudflare.com/cdn-cgi/trace', 200),
                ('google', 'https://www.google.com/generate_204', 204),
                ('openai', 'https://api.openai.com/v1/models', 401),
                ('anthropic', 'https://api.anthropic.com/v1/models', 401)
            ]:
                body = private / (name + '.body')
                start = time.monotonic()
                response = subprocess.run([
                    'curl', '--proxy', f'http://127.0.0.1:{proxy_port}', '--noproxy', '',
                    '--connect-timeout', '8', '--max-time', '20', '-sS', '-o', str(body),
                    '-w', '%{http_code}', url
                ], capture_output=True, text=True)
                item = {'test': name, 'status': response.stdout, 'seconds': round(time.monotonic() - start, 3),
                        'passed': response.returncode == 0 and response.stdout == str(expected)}
                if name == 'exit' and body.exists():
                    fields = dict(line.split('=', 1) for line in body.read_text().splitlines() if '=' in line)
                    item.update(exit_ip=fields.get('ip'), country=fields.get('loc'))
                    item['passed'] = item['passed'] and bool(item['exit_ip']) and bool(item['country'])
                    if args.expect_ip:
                        item['passed'] = item['passed'] and item['exit_ip'] == args.expect_ip
                    if args.expect_country:
                        item['passed'] = item['passed'] and item['country'] == args.expect_country.upper()
                if response.returncode:
                    item['error'] = redact(response.stderr[-300:], node)
                results.append(item)
                print(json.dumps(item), flush=True)
                if not item['passed']:
                    break
        finally:
            for child in [process, forward]:
                if child:
                    child.terminate()
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
            log.close()
    return 0 if len(results) == 4 and all(item['passed'] for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
