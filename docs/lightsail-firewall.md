# Opening the Lightsail firewall

1. Open the [Lightsail console](https://lightsail.aws.amazon.com/).
2. Choose the instance in the intended region, such as Tokyo (`ap-northeast-1`).
3. Open **Networking → IPv4 firewall → Add rule**.
4. Choose **Custom**, **TCP**, and port **443**.
5. Choose **Any IPv4 address** or the client source networks you intend to allow.
6. Save the rule and keep the existing SSH rule.

If the console shows “Restrict to IP address,” leaving it unchecked permits any
IPv4 source. A custom server port must match the firewall rule and client profile.

The cloud firewall and Linux firewall are separate. Check the service and listener:

```bash
sudo systemctl is-active lightsail-reality-clash
sudo ss -lntp 'sport = :443'
sudo ufw status
```

If UFW is already enabled, permit your chosen port using its normal rule mechanism:

```bash
sudo ufw allow 443/tcp
```

The installer does not enable, disable, or flush a host firewall. This guide uses
IPv4. An IPv6 endpoint also needs compatible listening and IPv6 firewall rules.

When diagnosing from a Mac with TUN enabled, a successful raw TCP connect can be
misleading: a local TUN stack may accept it before the external handshake finishes.
Use the isolated verifier with the physical interface, and require a successful
REALITY exchange and expected exit IP.

Do not change the server's public IPv4 address just to add a firewall rule.
