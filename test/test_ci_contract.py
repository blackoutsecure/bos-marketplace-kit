"""Keep required branch-protection checks backed by real PR jobs."""

from __future__ import annotations

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
    protection_steps = jobs["branch-protection"]["steps"]
    probe = next(
        step for step in protection_steps if "run" in step
    )
    assert probe["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert "secrets." not in str(protection_steps)
    assert "create-github-app-token" not in str(protection_steps)
    assert "Not Assessed" in probe["run"]
    assert "gh api graphql" in probe["run"]
    assert 'python3 "${helper}" from-graphql' in probe["run"]
    assert 'python3 "${helper}" compare' in probe["run"]
    assert "exit 1" in probe["run"]
