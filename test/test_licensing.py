"""Tests for the LC### licence audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from marketplace_kit import config, licensing  # noqa: E402

APACHE_HEADER = (
    "                                 Apache License\n"
    "                           Version 2.0, January 2004\n\n"
    "Copyright 2026 Blackout Secure\n"
)


def write(root: Path, name: str, body: str) -> None:
    (root / name).write_text(body, encoding="utf-8")


def statuses(audit: licensing.Audit) -> dict[str, str]:
    return {f.rule_id: f.status for f in audit.findings}


def message(audit: licensing.Audit, rule_id: str) -> str:
    return next(f.message for f in audit.findings if f.rule_id == rule_id)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------

def test_catalogue_is_valid_and_self_consistent():
    doc = licensing.catalogue()
    assert doc["source"] == "https://opensource.org/licenses"
    assert doc["licenses"] and doc["not_open_source"]
    for spdx, body in doc["licenses"].items():
        assert body["name"], spdx
        assert body["category"], spdx
        prefer = body.get("prefer")
        if prefer is not None:
            assert prefer in doc["licenses"], f"{spdx} prefers unknown {prefer}"
    # An identifier must not be both approved and not-open-source.
    assert not set(doc["licenses"]) & set(doc["not_open_source"])


def test_superseded_and_retired_entries_name_a_replacement():
    doc = licensing.catalogue()
    for spdx, body in doc["licenses"].items():
        if body["category"] in ("superseded", "retired"):
            assert body.get("prefer"), f"{spdx} has no suggested replacement"


@pytest.mark.parametrize("raw,expected", [
    ("Apache-2.0", "Apache-2.0"),
    ("apache-2.0", "Apache-2.0"),
    ("Apache%202.0", "Apache-2.0"),
    ("Apache License 2.0", "Apache-2.0"),
    ("MIT", "MIT"),
    ("GPL-3.0-or-later", "GPL-3.0-or-later"),
    ("GPL-2.0-only", "GPL-2.0-only"),
    ("LGPL-3.0+", "LGPL-3.0+"),
    ("BUSL-1.1", "BUSL-1.1"),
    ("Business Source License 1.1", "BUSL-1.1"),
    ("", "unknown"),
    ("Totally Made Up 9.9", "unknown"),
])
def test_normalise(raw, expected):
    assert licensing.normalise(raw) == expected


def test_distinct_spdx_identifiers_do_not_collide():
    # `GPL-3.0` and `GPL-3.0+` collapse to the same fuzzy key, so exact
    # matching has to win before the fuzzy tier is consulted.
    assert licensing.normalise("GPL-3.0") == "GPL-3.0"
    assert licensing.normalise("GPL-3.0+") == "GPL-3.0+"
    assert licensing.normalise("gpl-3.0") == "GPL-3.0"


def test_uncatalogued_suffix_falls_back_to_the_base_identifier():
    assert "MPL-2.0-or-later" not in licensing.catalogue()["licenses"]
    assert licensing.normalise("MPL-2.0-or-later") == "MPL-2.0"


def test_osi_approval():
    assert licensing.is_osi_approved("Apache-2.0")
    assert not licensing.is_osi_approved("BUSL-1.1")
    assert not licensing.is_osi_approved("unknown")


# ---------------------------------------------------------------------------
# Catalogue freshness
# ---------------------------------------------------------------------------

def test_vendored_snapshot_is_within_the_configured_max_age():
    limit = config.OPTIONS_BY_KEY["license_catalogue_max_age_days"].default
    age = licensing.catalogue_age_days()
    assert age >= 0, "osi-licenses.json has an unparseable `snapshot` date"
    assert age <= limit, (
        f"osi-licenses.json is {age} days old (limit {limit}) — the hub's "
        "`Refresh OSI licence catalogue` workflow has not landed in a while"
    )


def test_stale_catalogue_is_called_out_on_lc002(tmp_path, monkeypatch):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    monkeypatch.setattr(licensing, "catalogue_age_days", lambda *_a, **_k: 900)
    audit = licensing.audit(tmp_path, max_age_days=400)
    assert statuses(audit)["LC002"] == "pass"
    assert "900 days old" in message(audit, "LC002")


def test_fresh_catalogue_adds_no_note(tmp_path, monkeypatch):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    monkeypatch.setattr(licensing, "catalogue_age_days", lambda *_a, **_k: 10)
    assert "days old" not in message(licensing.audit(tmp_path), "LC002")


# ---------------------------------------------------------------------------
# LC001 / LC002 / LC003
# ---------------------------------------------------------------------------

def test_no_license_file_skips_every_rule(tmp_path):
    audit = licensing.audit(tmp_path)
    assert set(statuses(audit).values()) == {"skip"}
    assert set(statuses(audit)) == set(licensing.RULES)


def test_clean_apache_repo_passes(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "NOTICE", "Blackout Secure\n")
    audit = licensing.audit(tmp_path)
    assert audit.identifier == "Apache-2.0"
    assert audit.identifier_source == "LICENSE file"
    assert statuses(audit) == {
        "LC001": "pass", "LC002": "pass", "LC003": "pass",
        "LC004": "pass", "LC005": "pass", "LC006": "pass",
        "LC007": "pass",
    }


def test_unrecognised_license_warns_and_cascades_to_skip(tmp_path):
    write(tmp_path, "LICENSE", "All rights reserved. Ask us nicely.\n")
    audit = licensing.audit(tmp_path)
    assert audit.identifier == "unknown"
    result = statuses(audit)
    assert result["LC001"] == "warn"
    assert result["LC002"] == "skip"
    assert result["LC004"] == "skip"


def test_ai_identifier_is_a_fallback_and_stays_a_warning(tmp_path):
    write(tmp_path, "LICENSE", "Opaque bespoke text with no marker.\n")
    audit = licensing.audit(tmp_path, ai_identifier="MIT")
    assert audit.identifier == "MIT"
    assert audit.identifier_source == "ai"
    assert statuses(audit)["LC001"] == "warn"
    assert "low confidence" in message(audit, "LC001")


def test_ai_identifier_is_ignored_when_detection_succeeded(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    audit = licensing.audit(tmp_path, ai_identifier="MIT")
    assert audit.identifier == "Apache-2.0"
    assert audit.identifier_source == "LICENSE file"


def test_non_osi_license_is_flagged(tmp_path):
    write(tmp_path, "LICENSE", "SPDX-License-Identifier: BUSL-1.1\nCopyright 2026 X\n")
    audit = licensing.audit(tmp_path)
    assert statuses(audit)["LC002"] == "warn"
    assert "not OSI-approved" in message(audit, "LC002")
    assert statuses(audit)["LC003"] == "skip"


def test_superseded_license_suggests_the_replacement(tmp_path):
    write(tmp_path, "LICENSE", "SPDX-License-Identifier: EPL-1.0\nCopyright 2026 X\n")
    audit = licensing.audit(tmp_path)
    assert statuses(audit)["LC002"] == "pass"
    assert statuses(audit)["LC003"] == "warn"
    assert "`EPL-2.0`" in message(audit, "LC003")


def test_denied_list_beats_osi_approval(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    audit = licensing.audit(tmp_path, denied=("Apache-2.0",))
    assert statuses(audit)["LC002"] == "warn"
    assert "denied_licenses" in message(audit, "LC002")


def test_allowed_list_rejects_everything_else(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    assert statuses(licensing.audit(tmp_path, allowed=("MIT",)))["LC002"] == "warn"
    assert statuses(licensing.audit(tmp_path, allowed=("Apache-2.0",)))["LC002"] == "pass"


# ---------------------------------------------------------------------------
# LC004 — drift
# ---------------------------------------------------------------------------

def test_package_json_drift_is_reported(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "package.json", json.dumps({"name": "x", "license": "MIT"}))
    audit = licensing.audit(tmp_path)
    assert statuses(audit)["LC004"] == "warn"
    assert "package.json says `MIT`" in message(audit, "LC004")


def test_readme_badge_is_read_and_matched(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "README.md",
          "[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)\n")
    audit = licensing.audit(tmp_path)
    assert [d.identifier for d in audit.declarations] == ["Apache-2.0"]
    assert statuses(audit)["LC004"] == "pass"


def test_readme_badge_drift_is_reported(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "README.md",
          "[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)\n")
    assert statuses(licensing.audit(tmp_path))["LC004"] == "warn"


def test_pyproject_license_field_and_classifier(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "pyproject.toml", '[project]\nname = "x"\nlicense = "Apache-2.0"\n')
    assert statuses(licensing.audit(tmp_path))["LC004"] == "pass"

    write(tmp_path, "pyproject.toml",
          '[project]\nclassifiers = ["License :: OSI Approved :: MIT License"]\n')
    assert statuses(licensing.audit(tmp_path))["LC004"] == "warn"


def test_pyproject_license_file_pointer_is_not_a_declaration(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "pyproject.toml",
          '[project]\nname = "x"\nlicense = {file = "LICENSE"}\n')
    audit = licensing.audit(tmp_path)
    assert audit.declarations == ()
    assert statuses(audit)["LC004"] == "pass"


def test_no_other_surface_means_no_drift(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    audit = licensing.audit(tmp_path)
    assert audit.declarations == ()
    assert statuses(audit)["LC004"] == "pass"


def test_malformed_package_json_is_ignored(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    write(tmp_path, "package.json", "{not json")
    assert statuses(licensing.audit(tmp_path))["LC004"] == "pass"


# ---------------------------------------------------------------------------
# LC005 / LC006
# ---------------------------------------------------------------------------

def test_unfilled_template_placeholder_is_flagged(tmp_path):
    write(tmp_path, "LICENSE", "MIT License\n\nCopyright (c) [year] [fullname]\n")
    audit = licensing.audit(tmp_path)
    assert statuses(audit)["LC005"] == "warn"
    assert "placeholder" in message(audit, "LC005")


def test_missing_copyright_line_is_flagged(tmp_path):
    write(tmp_path, "LICENSE", "MIT License\n\nPermission is hereby granted...\n")
    assert statuses(licensing.audit(tmp_path))["LC005"] == "warn"


def test_copyright_may_live_in_notice(tmp_path):
    write(tmp_path, "LICENSE", "SPDX-License-Identifier: MIT\nPermission is granted.\n")
    write(tmp_path, "NOTICE", "Copyright (c) 2026 Blackout Secure\n")
    assert statuses(licensing.audit(tmp_path))["LC005"] == "pass"


def test_apache_without_notice_warns(tmp_path):
    write(tmp_path, "LICENSE", APACHE_HEADER)
    audit = licensing.audit(tmp_path)
    assert statuses(audit)["LC006"] == "warn"
    assert "4(d)" in message(audit, "LC006")


def test_notice_is_only_required_for_apache(tmp_path):
    write(tmp_path, "LICENSE", "SPDX-License-Identifier: MIT\nCopyright 2026 X\n")
    assert statuses(licensing.audit(tmp_path))["LC006"] == "skip"


# ---------------------------------------------------------------------------
# This repository audits clean
# ---------------------------------------------------------------------------

def test_this_repo_is_clean():
    audit = licensing.audit(Path(__file__).resolve().parents[1])
    assert audit.identifier == "Apache-2.0"
    assert not [f for f in audit.findings if f.status not in ("pass", "skip")]
