# Engineer dev-cluster trial

Target: AWS account `397229547211`, cluster `cbioportal-dev-36d15369`,
namespace `cbio-engineer-trial`. This is a temporary single-replica trial on
existing Spot capacity, not the final availability solution.

The pinned multi-architecture Hermes image runs without a Docker socket.
The terminal is local and Playwright runs directly. The cBio deployment MCP
and addon/Compose workflow are retired. Slack uses its outbound Socket Mode
connection; no public Service or Ingress is necessary.

## Storage and preparation

Apply `storage.yaml`, then `bootstrap.yaml` using the explicit dev kubeconfig.
The dedicated CSI storage class requests an encrypted 20 GiB gp3 disk. The
cluster's default gp2 class did not request encryption and was rejected by
the organization's `DenyUnencryptedVolumeCreation` policy. The dedicated class
does not change the default. Its Retain policy preserves the disk if the claim
is deleted; final cleanup must explicitly handle the retained volume.

The bootstrap pod has no Slack listener and no service-account token. Use it
to stage the current private profile, workspace and vault under the PVC's
`data`, `work` and `vault` directories. Do not commit credentials or archives.
Preserve the current working directory path so existing session references
continue to resolve. Copy the existing `runtime-patches/gateway-run.py` too;
the Deployment mounts this over the image's gateway implementation.

Exclude architecture-specific binaries, caches, old process IDs/locks and
preview process state. Install `playwright/install.sh` into
`/migration/data/tools/playwright-native` on the AMD64 bootstrap pod. The
package lock pins the browser version. Run `playwright/smoke.py` against its
launcher to check real navigation, JavaScript and PNG screenshots.

Install AMD64 ngrok and Tirith into the copied profile's `bin` directory.
The trial uses Tirith 0.5.0; its release archive SHA-256 is
`e2a87b1fbb967e8d37bc9c3c19bcd97f7979c9253e2f600d9293fce4d86d07ce`.
Keep the existing private ngrok configuration. Run `prepare-profile.py
/migration/data` to adjust the copied profile's runtime instructions and
Tirith path. The source profile on dev-macbook is unchanged.

Create the namespaced `engineer-env` Secret from the source profile's private
environment file. Never put token values in shell arguments or manifests
committed to Git. Set ownership of copied data/work files to UID/GID 10000,
the image's native Hermes identity. Using a different ID forces an expensive
recursive ownership change and overlay copy-up of the image's build trees
on every new pod.

## Cutover and rollback

`deployment.yaml` starts at zero replicas intentionally. Validate and stage it
before cutover. Stop the dev-macbook Engineer service before starting the
Kubernetes listener. Copy its final stopped SQLite/session state to the PVC;
never copy a live SQLite database without a consistent backup. Delete only
the bootstrap pod, then scale `deployment/engineer` to one replica.

Verify pod readiness, a fresh Slack Socket Mode connection in the gateway
log, and the browser smoke check inside the final pod. Readiness checks the
gateway process; it does not prove Slack authentication or an LLM response.
Verify those separately before declaring the trial ready.

For rollback, first scale the Kubernetes Deployment to zero and wait for its
pod to terminate. Then start the original Engineer service on dev-macbook.
Never run both Slack listeners simultaneously. New trial conversations live
on the PVC; preserve or reconcile them before treating rollback as a permanent
return to the Mac. Existing portal/companion containers on the Mac are outside
this trial and must not be stopped or deleted.

This directory contains no credentials. It does not provision an on-demand
node group or make the Spot-backed trial highly available.
