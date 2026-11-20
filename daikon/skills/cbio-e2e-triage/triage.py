#!/usr/bin/env python3
"""Read public cBioPortal frontend CI reports without credentials."""

import argparse
import json
import re
import sys
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

REPO = "cBioPortal/cbioportal-frontend"
GITHUB = f"https://api.github.com/repos/{REPO}"
CIRCLECI = "https://circleci.com/api/v2"
PROJECT = f"gh/{REPO}"
REPORT_PATH = "test-results/results.json"
REPORT_JOBS = {"remote_e2e", "e2e_localdb_merge"}
SHARD_JOBS = {"remote_e2e_shards", "e2e_localdb_shards"}
JOB_NAMES = REPORT_JOBS | SHARD_JOBS
TERMINAL_FAILURES = {"failed", "timedout", "canceled", "error", "infrastructure_fail"}
UUID = r"[0-9a-fA-F-]{36}"
CIRCLE_LINK = re.compile(rf"/workflow/({UUID})(?:/job/({UUID}))?/?")
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def get_json(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "cbio-e2e-triage"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def circle_reference(url):
    parsed = urlsplit(url)
    if parsed.scheme == "https" and parsed.hostname == "app.circleci.com":
        match = CIRCLE_LINK.fullmatch(parsed.path)
        if match:
            return match.groups()
    return None


def workflows_for(ref):
    explicit = circle_reference(ref)
    if explicit:
        workflow_id, job_id = explicit
        workflow = get_json(f"{CIRCLECI}/workflow/{workflow_id}")
        if workflow["project_slug"].lower() != PROJECT.lower():
            raise ValueError("Workflow belongs to a different CircleCI project")
        pipeline = get_json(f"{CIRCLECI}/pipeline/{workflow['pipeline_id']}")
        return pipeline.get("vcs", {}).get("revision"), {workflow_id: job_id}
    pr = re.fullmatch(rf"(?:https://github\.com/{REPO}/pull/)?(\d+)/?", ref, re.I)
    if pr:
        ref = get_json(f"{GITHUB}/pulls/{pr[1]}")["head"]["sha"]
    elif "://" in ref:
        raise ValueError("Use a cBioPortal frontend PR URL or a CircleCI workflow/job URL")
    status = get_json(f"{GITHUB}/commits/{quote(ref, safe='')}/status?per_page=100")
    workflows = {}
    for check in status["statuses"]:
        if check["context"] in {f"ci/circleci: {name}" for name in JOB_NAMES}:
            link = circle_reference(check.get("target_url") or "")
            if link:
                workflows[link[0]] = None
    return status["sha"], workflows


def circle_items(url):
    while url:
        page = get_json(url)
        yield from page["items"]
        token = page.get("next_page_token")
        if not token:
            return
        url = url.split("?", 1)[0] + "?page-token=" + quote(token, safe="")


def compact_error(error):
    message = error.get("message") or error.get("stack") or ""
    return ANSI.sub("", message).strip()[:2200]


def report_summary(report):
    def outcomes(suite, parents=()):
        titles = parents + (suite["title"],) if suite.get("title") else parents
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                if test.get("status") not in {"unexpected", "flaky"}:
                    continue
                attempts = []
                for result in test.get("results", []):
                    errors = result.get("errors") or ([result["error"]] if result.get("error") else [])
                    attempts.append({
                        "status": result.get("status"),
                        "errors": list(dict.fromkeys(filter(None, map(compact_error, errors)))),
                        "attachments": [
                            entry.get("path") or entry.get("name")
                            for entry in result.get("attachments", [])
                        ],
                    })
                yield {
                    "file": spec.get("file"),
                    "line": spec.get("line"),
                    "title": " › ".join(titles + (spec["title"],)),
                    "project": test.get("projectName"),
                    "status": test["status"],
                    "attempts": attempts,
                }
        for child in suite.get("suites", []):
            yield from outcomes(child, titles)

    return {
        "stats": report.get("stats", {}),
        "suite_errors": [compact_error(error) for error in report.get("errors", [])],
        "tests": [test for suite in report["suites"] for test in outcomes(suite)],
    }


def job_steps(job_number):
    url = f"https://circleci.com/api/v1.1/project/github/{REPO}/{job_number}"
    try:
        data = get_json(url)
    except (URLError, TimeoutError, ValueError):
        return []
    names = (
        action.get("name") or step.get("name")
        for step in data.get("steps", [])
        for action in step.get("actions", [])
        if action.get("failed") is True or (
            action.get("status") in TERMINAL_FAILURES
            and not (action.get("background") and action.get("status") == "canceled")
        )
    )
    return list(dict.fromkeys(filter(None, names)))


def job_summary(workflow_id, job):
    job_url = f"https://app.circleci.com/workflow/{workflow_id}/job/{job['id']}"
    summary = {
        "name": job["name"], "status": job["status"], "url": job_url,
        "job_number": job.get("job_number"),
    }
    if job.get("project_slug", "").lower() not in {"", PROJECT.lower()}:
        return {**summary, "unavailable": "Job belongs to a different CircleCI project"}
    if job.get("job_number") is None:
        return {**summary, "unavailable": "CircleCI has not assigned a job number"}
    try:
        artifacts = list(circle_items(
            f"{CIRCLECI}/project/{PROJECT}/{job['job_number']}/artifacts"
        ))
        summary["artifact_paths"] = [entry["path"] for entry in artifacts]
        report = next((entry for entry in artifacts if entry["path"] == REPORT_PATH), None)
        if report is None:
            if job["status"] in TERMINAL_FAILURES:
                summary["failed_steps"] = job_steps(job["job_number"])
            return {**summary, "unavailable": f"Job did not publish {REPORT_PATH}"}
        report_url = report["url"]
        if urlsplit(report_url).scheme != "https":
            return {**summary, "unavailable": "CircleCI returned a non-HTTPS report URL"}
        return {**summary, "report_url": report_url, **report_summary(get_json(report_url))}
    except (URLError, TimeoutError, ValueError, KeyError) as error:
        return {**summary, "unavailable": str(error)}


def triage(ref):
    sha, workflows = workflows_for(ref)
    found = []
    for workflow_id, requested_job in workflows.items():
        jobs = list(circle_items(f"{CIRCLECI}/workflow/{workflow_id}/job"))
        for job in jobs:
            if job["name"] not in JOB_NAMES:
                continue
            explicitly_requested = job["id"] == requested_job
            if (job["name"] in REPORT_JOBS
                    or explicitly_requested
                    or job["status"] in TERMINAL_FAILURES):
                found.append(job_summary(workflow_id, job))
    return {"reference": ref, "commit": sha, "jobs": found}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", help="GitHub PR number/URL, commit, branch, or CircleCI workflow/job URL")
    args = parser.parse_args()
    try:
        result = triage(args.reference)
    except (URLError, TimeoutError, ValueError, KeyError) as error:
        parser.exit(1, f"Could not read CI results: {error}\n")
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
