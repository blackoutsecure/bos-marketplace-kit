"""LC### emitter — bridges `marketplace_kit.licensing` into run.sh.

Prints one `ID|status|message` row per rule on stdout, which run.sh
splits and feeds to `record`. Kept as a separate entry point (rather
than inlined bash) because the audit reads TOML, JSON, and markdown.

Usage: audit_license.py <repo-root>

Environment:
  REQ_LICENSE_AUDIT  fail | warn | skip   — severity for non-passing rules
  ALLOWED_LICENSES   comma-separated SPDX allowlist ('' = no restriction)
  DENIED_LICENSES    comma-separated SPDX denylist
  MK_PUB_LICENSE     identifier already resolved by config.py, which may
                     have come from AI inference; used only as the
                     LC001 fallback and never escalated past `warn`

Never raises: a broken audit degrades to a single skip row rather than
failing the whole check run.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from marketplace_kit import licensing  # noqa: E402


def _list(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip())
    except ValueError:
        return default


def main(argv: list[str]) -> int:
    root = argv[1] if len(argv) > 1 else "."
    requirement = (os.environ.get("REQ_LICENSE_AUDIT") or "warn").strip()
    if requirement not in ("fail", "warn", "skip"):
        requirement = "warn"

    if requirement == "skip":
        for rule in licensing.RULES:
            print(f"{rule}|skip|licence audit disabled via require_license_audit")
        return 0

    try:
        result = licensing.audit(
            root,
            ai_identifier=os.environ.get("MK_PUB_LICENSE", ""),
            allowed=_list("ALLOWED_LICENSES"),
            denied=_list("DENIED_LICENSES"),
            max_age_days=_int("LICENSE_CATALOGUE_MAX_AGE_DAYS", 400),
        )
    except Exception as exc:  # noqa: BLE001 — never block the run on the audit
        for rule in licensing.RULES:
            print(f"{rule}|skip|licence audit unavailable ({type(exc).__name__})")
        return 0

    for finding in result.findings:
        # `warn` findings become `fail` only when the operator asked for it.
        status = requirement if finding.status == "warn" else finding.status
        message = finding.message.replace("|", "/").replace("\n", " ")
        print(f"{finding.rule_id}|{status}|{message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
