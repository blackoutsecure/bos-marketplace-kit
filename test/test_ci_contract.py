"""Keep required branch-protection checks backed by real PR jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_required_checks_have_pr_producers() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert workflow["on"]["pull_request"]["branches"] == ["dev"]
    jobs = workflow["jobs"]
    names = {job["name"] for key, job in jobs.items() if key != "analyze"}
    names.update(
        f"Analyze ({language})"
        for language in jobs["analyze"]["strategy"]["matrix"]["language"]
    )
    trusted = yaml.safe_load(
        (ROOT / ".github/workflows/protection-audit.yml").read_text(encoding="utf-8")
    )
    report = trusted["jobs"]["report"]["steps"][0]["run"]
    assert '"name": "Verify branch protection on main"' in report
    names.add("Verify branch protection on main")
    assert names == {
        "Python CLI (smoke + pytest)",
        "Analyze (python)",
        "Analyze (actions)",
        "Lint markdown / yaml / shell / actions",
        "Run check against own action.yml",
        "Render branding preview",
        "Verify branch protection on main",
    }
    assert all("if" not in job for job in jobs.values())
    scripts = "\n".join(step.get("run", "") for step in jobs["python-cli"]["steps"])
    assert "python -m pytest -q" in scripts
    assert "python -m ruff check src test scripts" in scripts
    for job, action in (
        ("check", "./.github/actions/check"),
        ("branding", "./.github/actions/branding-preview"),
        ("lint", "./.github/actions/lint"),
    ):
        assert any(step.get("uses") == action for step in jobs[job]["steps"])
    check_step = next(
        step for step in jobs["check"]["steps"]
        if step.get("uses") == "./.github/actions/check"
    )
    assert "fail_on_warning" not in check_step["with"]
    assert "secrets." not in str(workflow)
    assert "pull_request" not in trusted["on"]
    assert "pull_request_target" not in trusted["on"]
    assert trusted["on"]["workflow_run"]["workflows"] == [workflow["name"]]
    assert trusted["on"]["workflow_run"]["types"] == ["completed"]
    assert trusted["permissions"] == {"contents": "read"}
    assert trusted["jobs"]["report"]["permissions"] == {"checks": "write"}
    assert 'passed = os.environ["AUDIT_RESULT"] == "success"' in report
    assert '"conclusion": "success" if passed else "failure"' in report
    assert '"head_sha": os.environ["HEAD_SHA"]' in report
    audit = trusted["jobs"]["audit"]
    assert audit["permissions"] == {"contents": "read", "pull-requests": "read"}
    authorization_index = next(
        index for index, step in enumerate(audit["steps"])
        if step.get("uses", "").startswith("blackoutsecure/bos-workflow-gatekeeper@")
    )
    protection_index = next(
        index for index, step in enumerate(audit["steps"]) if step.get("id") == "protection"
    )
    assert authorization_index < protection_index
    assert audit["steps"][authorization_index]["with"]["actor"] == "${{ github.triggering_actor || github.actor }}"
    checkout = next(step for step in audit["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
    assert checkout["with"]["persist-credentials"] is False
    token = next(step for step in audit["steps"] if step.get("id") == "protection")
    assert token["with"]["permission-administration"] == "read"
    assert token["with"]["permission-contents"] == "read"
    probe = next(step for step in audit["steps"] if step.get("name") == "Read and compare actual protection")
    assert "Not Assessed" in probe["run"]
    assert 'gh api "repos/${REPOSITORY}/branches/main/protection"' in probe["run"]
    assert 'python3 "${helper}" compare' in probe["run"]
    assert "exit 1" in probe["run"]


def test_trusted_report_never_calls_an_unassessed_audit_successful() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/protection-audit.yml").read_text(encoding="utf-8")
    )
    step = workflow["jobs"]["report"]["steps"][0]
    assert step["env"]["AUDIT_RESULT"] == "${{ needs.audit.result }}"
    assert step["env"]["HEAD_SHA"] == "${{ needs.audit.outputs.head_sha }}"
    source = step["run"].split("\n", 2)[2].split("\nPY\n", 1)[0]
    for outcome in ("success", "failure", "cancelled", "skipped"):
        result = subprocess.run(
            [sys.executable, "-c", source],
            env=os.environ | {
                "AUDIT_RESULT": outcome,
                "HEAD_SHA": "a" * 40,
                "RUN_URL": "https://github.com/example/repo/actions/runs/1",
            },
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["head_sha"] == "a" * 40
        assert report["name"] == "Verify branch protection on main"
        assert report["conclusion"] == ("success" if outcome == "success" else "failure")


def test_trusted_audit_resolves_fork_pr_associations_without_head_code(tmp_path: Path) -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/protection-audit.yml").read_text(encoding="utf-8")
    )
    source = next(
        step["run"] for step in workflow["jobs"]["audit"]["steps"] if step.get("id") == "pull"
    )
    bash = shutil.which("bash")
    assert bash is not None, "The existing shell contract suite requires Bash."
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'case "$2" in\n'
        '  */commits/*/pulls*) cat fixture.json ;;\n'
        '  */pulls/14) printf "%s\\t%s\\tdev\\topen\\n" "${FIXTURE_HEAD}" "${REPOSITORY}" ;;\n'
        '  *) echo "Unexpected API request" >&2; exit 1 ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    for candidates, expected_success in (
        ([{"number": 14, "state": "open", "base": {"repo": {"full_name": "example/repo"}, "ref": "dev"}}], True),
        ([], False),
    ):
        (tmp_path / "fixture.json").write_text(json.dumps(candidates), encoding="utf-8")
        result = subprocess.run(
            [bash, "-s"],
            input='export PATH="$PWD/bin:$PATH"\n' + source,
            cwd=tmp_path,
            env=os.environ | {
                "EVENT_NAME": "workflow_run", "UPSTREAM_SHA": "b" * 40,
                "PULL_NUMBER": "", "REPOSITORY": "example/repo", "DEFAULT_BRANCH": "dev",
                "RUNNER_TEMP": ".", "GITHUB_OUTPUT": "outputs", "FIXTURE_HEAD": "a" * 40,
            },
            text=True,
            capture_output=True,
            check=False,
        )
        assert (result.returncode == 0) is expected_success, result.stderr
        if expected_success:
            assert (tmp_path / "outputs").read_text().splitlines() == [
                f"head_sha={'a' * 40}", "pull_number=14",
            ]
