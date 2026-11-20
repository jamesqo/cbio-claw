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

## E2E triage and disposable deployments

The engineering profile's `cbio-e2e-triage` skill reads public GitHub status
checks and CircleCI Playwright reports. Pass it a frontend PR, commit, branch,
or CircleCI job URL. The current cBioPortal frontend does not need a CircleCI
token for these reports.

The cBioPortal deployment MCP runs in a separate Docker container and uses
private Unix sockets for tool calls and browser forwarding. Deployment state
lives under `~/cbio-engineer/deployment-mcp-state`. The tool uses the existing
`work/checkouts` and `work/test-data` directories as read-only inputs. The
`cbio-daikon-deployment` skill explains which host paths to pass and how to
reach a ready test portal from Playwright.

On Daikon, use the pinned deployment MCP source to build its image:

```sh
git clone https://github.com/jamesqo/cbio-deployment-mcp.git
git -C cbio-deployment-mcp checkout --detach 1ee6d20e6b7bba7263f67b26a459e9dbf4bac226
docker build -t cbio-deployment-mcp:1ee6d20 cbio-deployment-mcp
```

With Engineer running and no deployment in progress, run
`bash daikon/install-integrations.sh` from this repository on Daikon. The
installer copies the skills and relay, starts the sidecar, and backs up any
engineering-profile configuration it changes. Restart
`hermes-cbio-engineer` to load the MCP and verify its Slack Socket Mode
connection. Check the MCP by listing deployments and try E2E triage against
a known failing frontend commit. If rolling back, restore the backed-up
engineering configuration and `SOUL.md`, remove these two profile-local skills, restart
Engineer, and stop the sidecar. Keep its state directory if there are
disposable deployments to recover.

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
