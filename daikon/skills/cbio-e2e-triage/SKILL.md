---
name: cbio-e2e-triage
description: Explain failing cBioPortal frontend Playwright E2E checks from a GitHub PR, commit, branch, or CircleCI job, using test reports and source at the tested revision.
---

# Explain cBioPortal E2E failures

Run `python3 /opt/data/profiles/engineering/skills/cbio-e2e-triage/triage.py REFERENCE`.
Accept a PR number or URL, a Git ref, or a CircleCI workflow/job URL. Use
`master` when the request is about the current default branch.

The script resolves the GitHub commit status and reads the public CircleCI API
for cBioPortal's frontend. It prints job status, the Playwright JSON report URL,
and failures and flakes with their assertion messages and retry outcomes.
Prefer the merged `remote_e2e` and `e2e_localdb_merge` reports for test results.
A failed shard, missing blob report, or setup failure can prevent test-level
evidence from being published. In that case inspect the job and shard links and
the reported failed CI steps. A step that just propagates the Playwright exit
code is evidence that the run failed, not a separate failure cause. Say when
the job did not publish enough evidence to explain the failure.

For each distinct failure, explain which observable check failed and what the
test expected. Use the source at the tested commit and any trace, screenshot, or
error artifact to identify a likely cause. Say when the available evidence only
shows a symptom. Separate failed tests, recovered retries, and suite or runner
failures. Say how many attempts were recorded. A failure with one recorded
attempt has no retry evidence. A claim that a failure predates the tested commit
needs an earlier failing run or reproduction at an earlier revision. Link the
CircleCI job or report and relevant source.

When reproduction is needed, use the tested revision of
`end-to-end-test-playwright` and match the remote or local-database job's target
and fixtures in its CircleCI config. Use the failing spec and title to limit the
rerun. Load `cbio-daikon-deployment` when a disposable backend with specific
refs or data is necessary. Keep CI results, local reproduction, and inferences
distinct.
