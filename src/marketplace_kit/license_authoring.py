"""Licence file generation, repair, and copyright maintenance.

Complements the read-only `LC###` audit: where that reports, this fixes.

Any of the OSI-approved identifiers in the vendored catalogue is
supported. Licence *text* is not vendored — 155 full texts would bloat
every consumer for a file most repos need once — so `--generate` fetches
it from the SPDX license list at the moment you ask for it. That is a
deliberate split: **verdicts stay offline and reproducible, authoring may
reach the network.** Nothing in the audit path ever makes a request.

Copyright handling is the fiddly part and is why this exists:

* several holders accumulate over a project's life,
* each carries their own set of years,
* the same holder gets spelled differently in different files,
* and the years want collapsing into ranges (`2019-2021, 2024`).

`merge_copyrights` in the shared catalogue module handles the union;
this module renders the result and writes it back consistently across
`LICENSE`, `NOTICE`, and the README header.

This is authoring assistance, not legal advice.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import NamedTuple

try:
    from . import licensing, osi_catalogue
except ImportError:  # executed as a loose script by the composite action
    from marketplace_kit import licensing, osi_catalogue

SPDX_TEXT_URL = "https://raw.githubusercontent.com/spdx/license-list-data/main/text/{id}.txt"

_TIMEOUT = 20

# A line that carries a copyright notice, for in-place rewriting.
_NOTICE_LINE = re.compile(r"copyright\s*(?:\((?:c|C)\)|©|&copy;)?\s*\d{4}", re.IGNORECASE)


class Result(NamedTuple):
    path: str
    action: str      # "created" | "updated" | "unchanged"
    detail: str


class LicenseTextError(RuntimeError):
    pass


def supported() -> tuple[str, ...]:
    """Every identifier this kit can generate, straight from the catalogue."""
    return tuple(sorted(licensing.catalogue()["licenses"]))


def fetch_text(identifier: str, *, url_template: str = SPDX_TEXT_URL) -> str:
    """Fetch canonical licence text for an OSI-approved identifier.

    Only called from authoring commands, never from an audit.
    """
    cat = licensing.catalogue()
    resolved = licensing.normalise(identifier)
    if resolved not in cat["licenses"]:
        raise LicenseTextError(
            f"`{identifier}` is not an OSI-approved identifier in the "
            f"{cat['snapshot']} catalogue snapshot. Run "
            "`marketplace-kit license --list` to see what is available.")
    request = urllib.request.Request(
        url_template.format(id=resolved),
        headers={"Accept": "text/plain", "User-Agent": "bos-marketplace-kit"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LicenseTextError(
            f"could not fetch the `{resolved}` text from the SPDX license "
            f"list ({type(exc).__name__}). Generation needs network access; "
            "the LC### audit does not.") from exc
    if not text.strip():
        raise LicenseTextError(f"the SPDX license list returned no text for `{resolved}`")
    return text


def fill_placeholders(text: str, holders: list[osi_catalogue.Copyright]) -> str:
    """Substitute a licence template's year/holder placeholders."""
    if not holders:
        return text
    primary = holders[0]
    years = osi_catalogue.format_years(primary.years) or str(dt.date.today().year)
    names = ", ".join(h.holder for h in holders if h.holder)
    replacements = (
        (r"\[yyyy\]", years),
        (r"\[year\]", years),
        (r"<year>", years),
        (r"\[name of copyright owner\]", names),
        (r"\[fullname\]", names),
        (r"\[name\]", names),
        (r"<name of author>", names),
        (r"<copyright holders?>", names),
    )
    for pattern, value in replacements:
        text = re.sub(pattern, value, text, flags=re.IGNORECASE)
    return text


def parse_holder_args(values: list[str], *, today: dt.date | None = None
                      ) -> list[osi_catalogue.Copyright]:
    """Parse `--holder "2019-2021 Acme Corp"` or a bare `"Acme Corp"`."""
    parsed: list[osi_catalogue.Copyright] = []
    current = (today or dt.date.today()).year
    for value in values:
        entries = osi_catalogue.parse_copyrights(f"Copyright {value}", today=today)
        if entries and entries[0].holder:
            parsed.append(entries[0])
        elif value.strip():
            parsed.append(osi_catalogue.Copyright(value.strip(), (current,), value))
    return parsed


def existing_holders(root: Path) -> list[osi_catalogue.Copyright]:
    """Every holder already claimed anywhere in the repo, merged."""
    surfaces = licensing.copyright_surfaces(root)
    return list(osi_catalogue.merge_copyrights(
        [entry for entries in surfaces.values() for entry in entries]))


def render_notice(holders: list[osi_catalogue.Copyright], *, symbol: str = "©") -> str:
    return "\n".join(h.render(symbol) for h in holders if h.holder)


def rewrite_notices(
    root: Path,
    holders: list[osi_catalogue.Copyright],
    *,
    files: tuple[str, ...] = ("NOTICE",),
    dry_run: bool = False,
) -> list[Result]:
    """Replace the copyright block in each named file with the merged roster."""
    results: list[Result] = []
    block = render_notice(holders)
    for name in files:
        path = root / name
        if not path.is_file():
            if dry_run:
                results.append(Result(name, "created", "would create"))
            else:
                path.write_text(block + "\n", encoding="utf-8")
                results.append(Result(name, "created", f"{len(holders)} holder(s)"))
            continue
        original = path.read_text(encoding="utf-8", errors="replace")
        replaced = _merge_notice_block(original, block)
        if replaced == original:
            results.append(Result(name, "unchanged", "already consistent"))
        elif dry_run:
            results.append(Result(name, "updated", "would rewrite the notice block"))
        else:
            path.write_text(replaced, encoding="utf-8")
            results.append(Result(name, "updated", f"{len(holders)} holder(s)"))
    return results


def _merge_notice_block(original: str, block: str) -> str:
    """Drop every existing notice line and put the merged block where the
    first one was, so surrounding prose keeps its position."""
    lines = original.split("\n")
    notice_at = [i for i, line in enumerate(lines) if _NOTICE_LINE.search(line)]
    if not notice_at:
        return block + "\n\n" + original
    kept = [line for i, line in enumerate(lines) if i not in set(notice_at)]
    kept.insert(notice_at[0], block)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept))


def generate(
    root: Path,
    identifier: str,
    holders: list[osi_catalogue.Copyright],
    *,
    dry_run: bool = False,
    fetch=fetch_text,
) -> list[Result]:
    """Write a LICENSE for `identifier`, with copyright filled in."""
    text = fill_placeholders(fetch(identifier), holders)
    resolved = licensing.normalise(identifier)
    if not text.rstrip().endswith("\n"):
        text = text.rstrip() + "\n"
    header = f"SPDX-License-Identifier: {resolved}\n\n"
    notice = render_notice(holders)
    body = header + (notice + "\n\n" if notice else "") + text

    path = root / "LICENSE"
    action = "updated" if path.is_file() else "created"
    if dry_run:
        return [Result("LICENSE", action, f"would write {resolved} ({len(body)} bytes)")]
    path.write_text(body, encoding="utf-8")
    return [Result("LICENSE", action, f"{resolved}, {len(holders)} holder(s)")]
