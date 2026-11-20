---
name: cbio-daikon-deployment
description: Deploy disposable cBioPortal instances on Daikon, import fixture studies, and test the resulting portal with its API or Playwright.
---

# cBioPortal acceptance testing on Daikon

- Use the `mcp_cbio_deployment_*` tools. Resolve the backend and importer
  refs independently. List deployments before choosing a port. Poll the
  deployment status and use operation logs to diagnose build or startup
  failures. Verify readiness with `api_request` against `/api/info`.
- Stage local checkouts in `checkouts/` and test studies in `test-data/` under
  the engineering workspace. The deployment MCP takes their host paths under
  `/home/koj2/cbio-engineer/work/`. It mounts inputs read-only and makes its
  own build and import copies.
- For Playwright, start the following as a background terminal process, using
  the deployment ID from `deploy` or `status` and a free local port:

  ```sh
  node /opt/data/cbio-deployment/deployment-mcp-relay.mjs portal-client \
    /opt/data/cbio-deployment/portal.sock DEPLOYMENT_ID 18080
  ```

  Open `http://127.0.0.1:18080` with the Playwright MCP. The forwarder works
  only for ready deployments owned by the deployment MCP. Stop the
  forwarder when finished.
- Exercise the requested behavior and report the backend/importer revisions,
  study IDs, and evidence. Save screenshots to the workspace's `artifacts/`
  directory. Clean up only disposable deployments from this task and retain
  the instance if the requester needs it for inspection.
