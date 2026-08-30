"""Licence audit — LC### rules.

`MP008` answers "is there a LICENSE file". This module answers the
questions that actually bite consumers: does the file resolve to a real
SPDX identifier, is that identifier OSI-approved, is it a superseded or
retired one, and does every other surface in the repo (README badge,
`pyproject.toml`, `package.json`, `NOTICE`) agree with it.

Deterministic by construction. The OSI catalogue is a vendored snapshot
in `data/osi-licenses.json`, never a runtime HTTP call: a policy verdict
must not depend on a third party being reachable, and the kit core is
stdlib-only. An AI-inferred identifier may be supplied by the caller for
`LC001` only, and never escalates a finding beyond `warn`.

None of this is legal advice.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import unquote

try:
    from . import metadata, osi_catalogue
except ImportError:  # executed as a loose script by the composite action
    from marketplace_kit import metadata, osi_catalogue

RULES = ("LC001", "LC002", "LC003", "LC004", "LC005", "LC006", "LC007")

# Spellings that appear in README badges and package manifests but are
# neither the SPDX id nor the OSI display name. Only this kit needs them:
# it reads free text, whereas a dependency SBOM only ever emits canonical
# SPDX.
_ALIASES = {
    "Apache 2.0": "Apache-2.0",
    "Apache License 2.0": "Apache-2.0",
    "Apache Software License": "Apache-2.0",
    "MIT License": "MIT",
    "BSD 3 Clause": "BSD-3-Clause",
    "BSD 2 Clause": "BSD-2-Clause",
    "GPLv3": "GPL-3.0",
    "GPLv2": "GPL-2.0",
    "LGPLv3": "LGPL-3.0",
    "AGPLv3": "AGPL-3.0",
    "MPL 2.0": "MPL-2.0",
    "EPL 2.0": "EPL-2.0",
    "BSL 1.1": "BUSL-1.1",
    "Business Source License 1.1": "BUSL-1.1",
    "Server Side Public License": "SSPL-1.0",
}

# OSI categories that mean "approved, but you probably want something else".
_DISCOURAGED = {
    "superseded": "superseded by a newer version of the same licence",
    "retired": "voluntarily retired by its steward",
}

# Placeholder text left behind by an unfilled licence template.
_PLACEHOLDER = re.compile(
    r"\[(?:year|yyyy|name|fullname|name of copyright owner|author)\]"
    r"|<(?:year|name|copyright holders?)>"
    r"|\byyyy\b|\bYOUR NAME\b|\bCOPYRIGHT HOLDER\b",
    re.IGNORECASE,
)

_COPYRIGHT = re.compile(r"copyright\s*(?:\(c\)|©|&copy;)?\s*\d{4}", re.IGNORECASE)

# The stock Apache-2.0 text ends with a fill-in-the-blanks appendix. Those
# placeholders are part of the licence, not an unfilled template.
_APPENDIX = re.compile(r"^[ \t]*APPENDIX:\s*How to apply", re.MULTILINE | re.IGNORECASE)


class Finding(NamedTuple):
    rule_id: str
    status: str   # pass | fail | warn | skip
    message: str


class Declaration(NamedTuple):
    surface: str     # human-readable origin, e.g. "package.json"
    identifier: str  # normalised SPDX identifier, or "unknown"
    raw: str         # what the surface literally said


class Audit(NamedTuple):
    identifier: str
    identifier_source: str        # "LICENSE file" | "ai" | "none"
    declarations: tuple[Declaration, ...]
    findings: tuple[Finding, ...]


# ---------------------------------------------------------------------------
# Catalogue — loading and identifier resolution live in the shared
# `osi_catalogue` module, synced from the hub alongside the data file.
# ---------------------------------------------------------------------------

def _loaded() -> osi_catalogue.Catalogue:
    return osi_catalogue.load(aliases=_ALIASES)


def catalogue() -> dict[str, Any]:
    """Return the vendored OSI snapshot. Cached; never hits the network."""
    return _loaded().document


def normalise(raw: str) -> str:
    """Map a licence spelling onto a catalogue identifier, or ``unknown``."""
    return _loaded().normalise(unquote(raw or ""))


def is_osi_approved(identifier: str) -> bool:
    return _loaded().is_osi_approved(identifier)


def catalogue_age_days(today: date | None = None) -> int:
    """Age of the vendored OSI snapshot in days, or -1 when unparseable."""
    return _loaded().age_days(today)


# Copyright parsing and merging are shared with the code-scanning kit.
Copyright = osi_catalogue.Copyright
parse_copyrights = osi_catalogue.parse_copyrights
merge_copyrights = osi_catalogue.merge_copyrights
format_years = osi_catalogue.format_years

# Files that may carry the project's copyright notice, in the order a
# reader is most likely to trust.
NOTICE_SURFACES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING",
                   "NOTICE", "NOTICE.md", "README.md")


def copyright_surfaces(root: Path | str = ".") -> dict[str, tuple[Copyright, ...]]:
    """Every copyright notice the repository states about itself, by file.

    The Apache-2.0 appendix is stripped first: its `Copyright [yyyy]
    [name of copyright owner]` is licence boilerplate, not a claim.
    """
    root = Path(root)
    surfaces: dict[str, tuple[Copyright, ...]] = {}
    for name in NOTICE_SURFACES:
        path = root / name
        if not path.is_file():
            continue
        body = _APPENDIX.split(_read(path, 20_000))[0]
        found = tuple(c for c in parse_copyrights(body) if c.holder)
        if found:
            surfaces[name] = found
    return surfaces


# ---------------------------------------------------------------------------
# Surface readers
# ---------------------------------------------------------------------------

def _read(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _from_pyproject(root: Path) -> Declaration | None:
    text = _read(root / "pyproject.toml")
    if not text:
        return None
    # `license = "MIT"` or `license = {text = "MIT"}`, then a trove
    # classifier. `license = {file = "LICENSE"}` is a pointer to the file
    # this audit already read, so it cannot disagree with it.
    match = re.search(
        r"^\s*license\s*=\s*(?:\{\s*text\s*=\s*)?[\"']([^\"']+)[\"']",
        text, re.MULTILINE | re.IGNORECASE)
    if match:
        return Declaration("pyproject.toml", normalise(match.group(1)), match.group(1))
    classifier = re.search(
        r"[\"']License :: OSI Approved :: ([^\"']+)[\"']", text)
    if classifier:
        raw = classifier.group(1)
        return Declaration("pyproject.toml (classifier)", normalise(raw), raw)
    return None


def _from_package_json(root: Path) -> Declaration | None:
    text = _read(root / "package.json")
    if not text:
        return None
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return None
    raw = doc.get("license") if isinstance(doc, dict) else None
    if isinstance(raw, dict):
        raw = raw.get("type")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Declaration("package.json", normalise(raw), raw.strip())


def _from_readme(root: Path) -> Declaration | None:
    for name in ("README.md", "README", "Readme.md", "readme.md"):
        path = root / name
        if not path.is_file():
            continue
        text = _read(path, 65_536)
        # shields.io style: .../badge/License-Apache%202.0-blue
        badge = re.search(
            r"shields\.io/badge/[Ll]icen[cs]e-([^-\]\)\s]+)-", text)
        if badge:
            return Declaration(f"{name} (badge)", normalise(badge.group(1)),
                               unquote(badge.group(1)))
        inline = re.search(
            r"^.*\blicen[cs]ed?\b[^\n]*?\b("
            r"Apache(?:[ -]License)?[ -]?2(?:\.0)?"
            r"|MIT|BSD[ -][23][ -]Clause|MPL[ -]?2\.0|EPL[ -]?2\.0"
            r"|A?GPL[ -]?v?[23](?:\.0)?|ISC|Unlicense)\b",
            text, re.IGNORECASE | re.MULTILINE)
        if inline:
            return Declaration(f"{name}", normalise(inline.group(1)), inline.group(1))
        return None
    return None


def declarations(root: Path | str = ".") -> tuple[Declaration, ...]:
    """Every licence claim the repo makes outside the LICENSE file."""
    root = Path(root)
    found = (_from_readme(root), _from_pyproject(root), _from_package_json(root))
    return tuple(d for d in found if d is not None)


def _license_path(root: Path) -> Path | None:
    for name in metadata.license_files():
        path = root / name
        if path.is_file():
            return path
    return None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def audit(
    root: Path | str = ".",
    *,
    ai_identifier: str = "",
    allowed: tuple[str, ...] = (),
    denied: tuple[str, ...] = (),
    max_age_days: int = 400,
) -> Audit:
    """Run LC001-LC006 against ``root``.

    ``ai_identifier`` is consulted only when the deterministic readers
    cannot classify the LICENSE file, and only ever produces a ``warn``.
    ``max_age_days`` bounds how old the vendored OSI snapshot may be
    before LC002 says its verdict might be out of date.
    """
    root = Path(root)
    doc = catalogue()
    path = _license_path(root)

    age = catalogue_age_days()
    stale = ""
    if 0 <= max_age_days < age:
        stale = (f" (OSI snapshot {doc['snapshot']} is {age} days old, over the "
                 f"{max_age_days}-day limit — refresh `osi-licenses.json`)")

    if path is None:
        skipped = tuple(
            Finding(rule, "skip", "no LICENSE file at the repo root (see MP008)")
            for rule in RULES
        )
        return Audit("unknown", "none", declarations(root), skipped)

    text = _read(path)
    identifier = normalise(metadata.read_repo_license(root))
    source = "LICENSE file"
    if identifier == "unknown" and ai_identifier:
        inferred = normalise(ai_identifier)
        if inferred != "unknown":
            identifier, source = inferred, "ai"

    declared = declarations(root)
    findings: list[Finding] = []

    # ----- LC001: the LICENSE file resolves to a known identifier -----
    if identifier == "unknown":
        findings.append(Finding(
            "LC001", "warn",
            f"`{path.name}` does not resolve to a known SPDX identifier — "
            "GitHub's licence detection, npm, and consumer policy bots will "
            "read it as `NOASSERTION`. Add an `SPDX-License-Identifier:` line "
            "or paste the unmodified upstream licence text"))
    elif source == "ai":
        findings.append(Finding(
            "LC001", "warn",
            f"`{path.name}` was classified as `{identifier}` by AI inference "
            "(low confidence) because deterministic detection failed — add an "
            "explicit `SPDX-License-Identifier:` line to make it unambiguous"))
    else:
        findings.append(Finding(
            "LC001", "pass",
            f"`{path.name}` resolves to `{identifier}`"))

    # ----- LC002: OSI-approved, and inside org policy -----------------
    denied_hit = next(
        (d for d in denied if normalise(d) == identifier and identifier != "unknown"),
        "")
    if identifier == "unknown":
        findings.append(Finding("LC002", "skip", "identifier unresolved (see LC001)"))
    elif denied_hit:
        findings.append(Finding(
            "LC002", "warn",
            f"`{identifier}` is on this repository's `denied_licenses` list"))
    elif allowed and not any(normalise(a) == identifier for a in allowed):
        findings.append(Finding(
            "LC002", "warn",
            f"`{identifier}` is not on this repository's `allowed_licenses` "
            f"list ({', '.join(allowed)})"))
    elif identifier in doc["not_open_source"]:
        findings.append(Finding(
            "LC002", "warn",
            f"`{identifier}` is not OSI-approved — "
            f"{doc['not_open_source'][identifier]}. Consumers with an "
            "open-source-only policy cannot take a dependency on this action. "
            "See https://opensource.org/licenses"))
    elif is_osi_approved(identifier):
        findings.append(Finding(
            "LC002", "pass",
            f"`{identifier}` is OSI-approved "
            f"({doc['licenses'][identifier]['category']}){stale}"))
    else:
        findings.append(Finding(
            "LC002", "warn",
            f"`{identifier}` is not in the OSI approved list "
            f"(snapshot {doc['snapshot']}) — confirm it at "
            "https://opensource.org/licenses, or switch to an approved licence"))

    # ----- LC003: category health -------------------------------------
    entry = doc["licenses"].get(identifier)
    if entry is None:
        findings.append(Finding("LC003", "skip", "not an OSI-approved licence (see LC002)"))
    elif entry["category"] in _DISCOURAGED:
        prefer = entry.get("prefer")
        advice = f" — use `{prefer}` instead" if prefer else ""
        findings.append(Finding(
            "LC003", "warn",
            f"`{identifier}` is {_DISCOURAGED[entry['category']]}{advice}"))
    else:
        findings.append(Finding(
            "LC003", "pass",
            f"`{identifier}` is in good standing (OSI category: {entry['category']})"))

    # ----- LC004: no drift across the repo's other surfaces -----------
    if identifier == "unknown":
        findings.append(Finding("LC004", "skip", "identifier unresolved (see LC001)"))
    elif not declared:
        findings.append(Finding(
            "LC004", "pass",
            "no other surface declares a licence, so nothing can drift"))
    else:
        drift = [d for d in declared if d.identifier != identifier]
        if drift:
            detail = "; ".join(
                f"{d.surface} says `{d.raw}`"
                f"{'' if d.identifier == 'unknown' else f' (`{d.identifier}`)'}"
                for d in drift)
            findings.append(Finding(
                "LC004", "warn",
                f"licence drift — `{path.name}` says `{identifier}` but "
                f"{detail}. Consumers read whichever surface they hit first"))
        else:
            findings.append(Finding(
                "LC004", "pass",
                f"all {len(declared)} declared surface(s) agree on `{identifier}`"))

    # ----- LC005: copyright line is present and filled in -------------
    notice = _read(root / "NOTICE") + _read(root / "NOTICE.md")
    readme = next((_read(root / n, 4096) for n in
                   ("README.md", "README", "Readme.md", "readme.md")
                   if (root / n).is_file()), "")
    body = _APPENDIX.split(text)[0]
    placeholder = _PLACEHOLDER.search(body)
    if placeholder:
        findings.append(Finding(
            "LC005", "warn",
            f"`{path.name}` still contains the unfilled template placeholder "
            f"`{placeholder.group(0)}` — replace it with the copyright year "
            "and holder"))
    elif any(_COPYRIGHT.search(source) for source in (body, notice, readme)):
        findings.append(Finding("LC005", "pass", "copyright line present and filled in"))
    else:
        findings.append(Finding(
            "LC005", "warn",
            f"no `Copyright <year> <holder>` line found in `{path.name}`, "
            "`NOTICE`, or the README header — most licences require the "
            "notice to name a holder"))

    # ----- LC006: Apache-2.0 attribution NOTICE -----------------------
    if identifier != "Apache-2.0":
        findings.append(Finding(
            "LC006", "skip", "NOTICE is only required for Apache-2.0"))
    elif notice.strip():
        findings.append(Finding("LC006", "pass", "`NOTICE` present alongside Apache-2.0"))
    else:
        findings.append(Finding(
            "LC006", "warn",
            "Apache-2.0 section 4(d) expects a `NOTICE` file when the work "
            "carries attribution notices — add one at the repo root"))

    # ----- LC007: the copyright story is consistent -------------------
    surfaces = copyright_surfaces(root)
    if not surfaces:
        findings.append(Finding(
            "LC007", "skip", "no copyright notice found to cross-check (see LC005)"))
    else:
        by_holder: dict[str, set[str]] = {}
        for filename, entries in surfaces.items():
            for entry in entries:
                by_holder.setdefault(entry.holder.casefold(), set()).add(filename)
        everywhere = set(surfaces)
        partial = {
            holder: sorted(everywhere - files)
            for holder, files in by_holder.items()
            if files != everywhere
        }
        merged = merge_copyrights(
            [entry for entries in surfaces.values() for entry in entries])
        roster = "; ".join(
            f"`{c.holder}` ({format_years(c.years) or 'no year'})" for c in merged)
        if partial:
            detail = "; ".join(
                f"`{holder}` is missing from {', '.join(f'`{f}`' for f in files)}"
                for holder, files in sorted(partial.items()))
            findings.append(Finding(
                "LC007", "warn",
                f"copyright attribution differs across surfaces — {detail}. "
                f"Merged roster: {roster}. Reconcile with "
                "`marketplace-kit license --fix`"))
        elif len(merged) > 1:
            findings.append(Finding(
                "LC007", "pass",
                f"{len(merged)} copyright holders are named consistently across "
                f"{len(surfaces)} surface(s): {roster}"))
        else:
            findings.append(Finding(
                "LC007", "pass",
                f"copyright attribution is consistent across "
                f"{len(surfaces)} surface(s): {roster}"))

    return Audit(identifier, source, declared, tuple(findings))
