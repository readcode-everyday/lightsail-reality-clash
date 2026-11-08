# Troubleshooting

## REALITY authentication failed

For the tested modern Xray version, the client needs:

```yaml
client-fingerprint: chrome
reality-opts:
  public-key: REPLACE_WITH_GENERATED_PUBLIC_KEY
  short-id: REPLACE_WITH_GENERATED_SHORT_ID
  support-x25519mlkem768: true
```

The public key, short ID, UUID, server name and Vision flow must match the server
configuration. The generator includes these settings automatically. Check clock
synchronization as well. A newer Xray version does not guarantee compatibility with
every client release or browser fingerprint; keep the tested version pairing in
mind when upgrading.

See [the Xray maintainer's compatibility guidance](https://github.com/XTLS/Xray-core/issues/7259)
and [Mihomo's TLS options](https://wiki.metacubex.one/en/config/proxies/tls/).

## Public timeout but the SSH tunnel test works

Check both the [Lightsail firewall](lightsail-firewall.md) and the host firewall.
Confirm you edited the correct region and instance. A service listening locally is
not enough to establish that the cloud port is open.

## Wrong exit IP or a successful test using the wrong node

Use the verifier's `--interface` option to bind the isolated process to the physical
interface when needed. Confirm your active proxy group's selection after importing
the new profile. An existing service-specific group can still select another node.
Merged profiles retain those groups and rules.

## `.cn` or `.gov` does not go direct

Those rules are only added with `--direct-cn-gov`. Use Rule mode, and check that an
earlier rule does not override the intended policy. DIRECT traffic exposes the
local connection's exit IP to its destination.

## An API returns 401

The verifier deliberately sends no API key. A 401 is expected in these checks.
Authenticated inference, model availability and account access are separate tests.
A 403, TLS failure or timeout needs further investigation.

## Sharing diagnostics

Share software versions, status codes and redacted error messages. Keep generated
client JSON, server private keys, UUID access credentials, subscription URLs and
full profiles out of public issues and screenshots.
