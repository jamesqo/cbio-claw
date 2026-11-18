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

## Dedicated group: pending admin provisioning

As of 2026-11-18, Engineer still runs on addons. Both ON_DEMAND and SPOT
CreateNodegroup requests were denied: the decoded error reports an explicit
ec2:RunInstances deny for mskEngineerUser. No dedicated group was created.

An authorized infrastructure administrator can review and submit the request:

```sh
aws eks create-nodegroup --region us-east-1 --cli-input-json file://nodegroup.json
aws eks wait nodegroup-active --region us-east-1 --cluster-name cbioportal-dev-36d15369 --nodegroup-name engineer-spot
```

Use credentials for account 397229547211. The request places one Spot node in
us-east-1a, matching the existing disk, with several compatible instance types.
It reuses the addons IAM role and immutable launch-template version 4 (encrypted
boot disk and existing security groups). The template's EC2 resource tags still
name addons; the administrator should account for those inherited tags or supply
an equivalent dedicated template. This separates capacity, not IAM privileges.
The workload taint excludes ordinary untolerated pods; system DaemonSets may
still run there. Single-zone placement prevents cross-zone rebalancing, but
does not prevent Spot reclamation.

After creation, set KUBECONFIG to the explicit dev kubeconfig and run:

```sh
kubectl wait node -l eks.amazonaws.com/nodegroup=engineer-spot --for=condition=Ready --timeout=300s
kubectl -n cbio-engineer-trial patch deployment engineer --type=strategic --patch-file dedicated-node-patch.yaml --dry-run=server
kubectl -n cbio-engineer-trial patch deployment engineer --type=strategic --patch-file dedicated-node-patch.yaml
kubectl -n cbio-engineer-trial rollout status deployment/engineer --timeout=300s
kubectl -n cbio-engineer-trial get pods -o wide
kubectl get nodes -L eks.amazonaws.com/nodegroup,eks.amazonaws.com/capacityType
```

The patch preserves the live replica count. Recreate stops the existing listener
before starting the replacement; allow for disk transfer and image download.
Verify the pod runs on engineer-spot, Slack reconnects, and a user message receives
a reply before declaring completion. Do not apply the patch before capacity is
ready. For future deployments retain this patch with the base manifest: the base
alone stages zero replicas and does not select the dedicated node group.
