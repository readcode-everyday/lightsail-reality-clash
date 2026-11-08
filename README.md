# Lightsail REALITY + Clash

A small deployment kit for a self-hosted **VLESS + REALITY + XTLS Vision** node,
with a dedicated Linux service, Mihomo/Clash profile generation, and isolated
connection tests. Designed around AWS Lightsail and macOS, with configurable
server addresses, profile groups, and client paths.

```text
Mac / Mihomo ── REALITY + Vision over TCP 443 ── Lightsail ── destination
```

No additional commercial proxy hop or personally owned domain is required.
REALITY uses a configured TLS handshake target. The destination sees the server's
exit IP. Network observers can still see the server IP, connection timing and
traffic volume; this does not promise that proxy use is undetectable.

## What is included

- Download a pinned official Xray release and check its published SHA256.
- Generate credentials on the server and run Xray under a dedicated service account.
- Generate a standalone profile, merge into an exported profile, or create a
  Clash Party JavaScript override.
- Keep existing nodes, routing rules and DNS settings when merging a profile.
- Test the exit IP and endpoint reachability without changing the active client.

This repository contains source and placeholder examples. Private keys, deployed
UUIDs, subscription profiles, generated client files and deployment logs are not
included. All installation and generated outputs stay local.

## Requirements and tested versions

| Component | Requirement / validation |
|---|---|
| Server | Ubuntu with systemd, Python 3.10+, sudo; x86_64 or aarch64 |
| Xray | Default pinned release: **26.10.31** |
| Client tooling | Node.js 20+, Python 3.10+, curl, an installed Mihomo binary |
| Reference deployment | Ubuntu 24.04 x86_64, Clash Party 1.9.5, Mihomo 1.19.24 |
| REALITY client | Chrome fingerprint and `support-x25519mlkem768: true` |

The reference deployment passed public TCP 443, exit-IP, Google and unauthenticated
OpenAI/Anthropic endpoint checks. The portable installer has local automated tests;
a clean-VM install is not part of the automated test suite. ARM64 is supported by
asset selection but has not been exercised in the reference deployment.

## 1. Install on the server

Create an Ubuntu Lightsail instance and verify that SSH works. In the examples,
`vps` is your SSH alias and **203.0.113.10 is a documentation address**: replace it
with your own server's public IPv4 address.

Clone this repository locally and review the installer:

```bash
git clone https://github.com/readcode-everyday/lightsail-reality-clash.git
cd lightsail-reality-clash
python3 scripts/install-server.py --server 203.0.113.10 --dry-run
scp scripts/install-server.py vps:/tmp/install-reality.py
ssh vps 'sudo python3 /tmp/install-reality.py --server 203.0.113.10 --name My-Reality'
```

The installer validates TLS 1.3 / HTTP/2 support on the handshake target before
installing. `--target` selects a different hostname; `--version` selects an explicit
release. It uses Python's standard library and does not execute a downloaded shell
installer. The checksum comes from the same official release as the archive.

The service starts at boot. Its files are isolated from other Xray installations:

| File | Location |
|---|---|
| Service | `lightsail-reality-clash.service` |
| Binary | `/usr/local/lib/lightsail-reality-clash/xray` |
| Server configuration | `/etc/lightsail-reality-clash/config.json` |
| Private client export | `/var/lib/lightsail-reality-clash/client.json` |

An existing project installation is refused by default. `--replace` creates a
private backup and **generates new credentials**, requiring a new client import.
It does not edit SSH configuration or the cloud firewall.

## 2. Open the Lightsail firewall

In **Tokyo instance → Networking → IPv4 firewall**, add:

| Field | Value |
|---|---|
| Application | Custom |
| Protocol | TCP |
| Port | 443 |
| Source | Any IPv4 address, or your intended client networks |

Keep the SSH rule. The Ubuntu host firewall must also permit the chosen port.
See [the firewall guide](docs/lightsail-firewall.md).

## 3. Retrieve the private client export

Use a private local folder; do not paste the export into an issue or commit it:

```bash
mkdir -p private
chmod 700 private
umask 077
ssh vps 'sudo cat /var/lib/lightsail-reality-clash/client.json' > private/client.json
npm ci --ignore-scripts
```

Generate a standalone profile:

```bash
node scripts/configure-clash.cjs \
  --client private/client.json \
  --output generated/reality.yaml
```

Import the generated local YAML into your Mihomo-based client. Select the new node
in its proxy group. TUN is an optional **client-side** setting; the server does not
need TUN to accept REALITY connections. Normal macOS and client DNS settings are
not changed by these scripts.

To extend an existing exported profile:

```bash
node scripts/configure-clash.cjs \
  --client private/client.json \
  --input private/existing-profile.yaml \
  --output generated/combined.yaml \
  --group 'Proxy'
```

`--group` can be repeated. Without it, the tool chooses matching select groups or
creates a standalone group. The source profile is kept intact; output formatting
is normalized and comments may change. The tool adds the node but does not change
existing group selections or reroute existing service-specific groups.

For Clash Party, create an override and attach it to the profiles you choose in
the application's override settings:

```bash
node scripts/configure-clash.cjs \
  --client private/client.json \
  --override-output generated/reality.js
```

Generated YAML and JavaScript contain access credentials. A merged profile may also
contain your existing subscription credentials. Both `private/` and `generated/`
are ignored by Git. Public examples belong in `examples/` with placeholders only.

### Optional direct rules

Add `--direct-cn-gov` to prepend `.cn` and `.gov` DIRECT rules. This is opt-in:
these requests then use your local connection and its public IP. Use **Rule mode**
for split routing; Global mode bypasses routing rules.

## 4. Verify before switching

Run the checks with your installed Mihomo executable:

```bash
python3 scripts/verify-node.py \
  --client private/client.json \
  --mihomo '/Applications/Clash Party.app/Contents/Resources/sidecar/mihomo' \
  --interface en0 \
  --expect-country JP \
  --expect-ip 203.0.113.10
```

Use your actual physical interface; omit `--interface` when it is unnecessary.
The checker uses a temporary private configuration with TUN disabled and temporary
loopback listeners. It stops its own processes and deletes its temporary files.
It does not reload or modify your active Clash instance.

Expected results are Cloudflare trace 200, Google 204, and OpenAI/Anthropic 401.
The 401 responses verify unauthenticated network reachability, **not** a successful
model call or account entitlement. Endpoint behavior can change.

If public access is blocked, `--ssh-host vps` tests through a temporary SSH tunnel.
Omit `--interface` in that case. A tunnel test does not prove public port 443 works.

## Local tests

```bash
npm ci --ignore-scripts
npm test
python3 -m unittest discover -s tests -p 'test_*.py'
```

Fixtures use documentation addresses and synthetic values, with no working
credentials. See [troubleshooting](docs/troubleshooting.md) for handshake and
firewall failures, and [maintenance](docs/maintenance.md) for service management.

## Upstream projects and licenses

The original scripts and documentation here use the [MIT license](LICENSE).
Third-party software retains its own license and is not bundled:

- [Xray-core](https://github.com/XTLS/Xray-core) — [MPL-2.0](https://github.com/XTLS/Xray-core/blob/main/LICENSE)
- [REALITY protocol and examples](https://github.com/XTLS/REALITY)
- [Mihomo](https://github.com/MetaCubeX/mihomo) — [GPL-3.0](https://github.com/MetaCubeX/mihomo/blob/Meta/LICENSE)
- [yaml](https://github.com/eemeli/yaml) — ISC

Compatibility references: [Mihomo TLS configuration](https://wiki.metacubex.one/en/config/proxies/tls/)
and the [Xray maintainer's modern-handshake guidance](https://github.com/XTLS/Xray-core/issues/7259).
