# Service maintenance

The portable installer uses its own service and paths; it does not take over an
unrelated `xray.service`.

```bash
sudo systemctl status lightsail-reality-clash
sudo journalctl -u lightsail-reality-clash --since '10 minutes ago'
sudo systemctl restart lightsail-reality-clash
```

To stop it and prevent boot startup:

```bash
sudo systemctl disable --now lightsail-reality-clash
```

Configuration and private state remain available for recovery. Do not publish
those files or backups.

The first installation refuses occupied listening ports. Reinstalling this
project requires `--replace`, which backs up its files under its private state
directory and rotates access credentials. Import the new client export afterward.
The installer does not delete its old backups automatically.

To restore a backup, stop the service, restore the matching binary, configuration,
unit and client export together, preserve their ownership and permissions, run
`systemctl daemon-reload`, and start the service. Restoring only the client export
does not restore the server-side credentials.

Upgrades should be tested using an isolated client before changing an active
selection. The version flag pins the downloaded release; the upstream project can
change compatibility requirements between versions.
