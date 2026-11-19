# Engineer on Daikon

Cut over on 2026-11-19. Daikon runs hermes-cbio-engineer; the EKS trial is
scaled to zero and dev-macbook's copy is stopped. The EKS PVC remains available
for rollback. Slack authentication and Socket Mode connection, native browser
operations, model inference and both SQLite integrity checks were verified.

Target: on-demand EC2 i-0171dd67eaf4079e3 (daikondev), login koj2.
The container uses the same pinned image and internal paths as the EKS trial.
It has a 2 CPU / 4 GiB limit, bounded Docker logs, and no Docker socket mount.

Host data is under /home/koj2/cbio-engineer/{data,work,vault}. The root disk
has limited headroom; monitor usage and move this directory to an approved
location on /data2 when an administrator provides one. /data2/koj2 currently
belongs to a different numeric UID and is not writable by this account.

## Migration procedure

Stage a copy of the PVC contents without starting the gateway. Validate native
Playwright and model access on the target. Stop the EKS Deployment (replicas=0)
and wait for its gateway pod to terminate. Copy the final databases, sessions,
memories and profile settings from the stopped source, checking SQLite integrity.
Remove only stale runtime lock/PID files in the destination. Keep credentials
private and out of Git. Prepare the destination profile using prepare-profile.py
with the data mounted at /opt/data; set data/work ownership to container UID/GID
10000. Run start-engineer.sh only after the previous listener is stopped.

Copy the EKS engineer-env Secret into a mode-0600 runtime.env file in the host
directory. The launch script passes this to Docker; the profile's .env alone
does not contain all runtime provider credentials. Never commit either file.

Verify Slack Socket Mode connects, browser tools work, and a user message gets
an inline reply. Preserve the source PVC for rollback. For rollback stop Daikon's
hermes-cbio-engineer container before scaling the EKS Deployment back to one.
New conversation state on Daikon must be reconciled before permanent rollback.

## Tailscale without sudo

Tailscale 1.104.7 static binaries are in ~/.local/opt/tailscale. Its private state
and socket are in ~/.local/state/tailscale. start-tailscale.sh runs a userspace
daemon with a loopback SOCKS proxy on port 1055. A per-user cron job invokes the
script every minute; flock ensures one instance. It restarts after reboot or
process exit without sudo. The log resets on daemon start.

The enrolled name is daikon (100.70.130.64). Tailscale Serve forwards tailnet
TCP port 22 to the host's existing SSH service on 127.0.0.1:22. SSH still requires
the existing host credentials. No subnet routes, exit-node routing or public
Funnel are configured. This does not provide a system-wide VPN interface.

```sh
~/.local/opt/tailscale/tailscale --socket="$HOME/.local/state/tailscale/tailscaled.sock" status
~/.local/opt/tailscale/tailscale --socket="$HOME/.local/state/tailscale/tailscaled.sock" serve status
```
