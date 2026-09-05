# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## What this is

`bos-marketplace-kit` is a GitHub Marketplace composite Action plus a local CLI that
validate whether a repository is ready to be published as a Marketplace Action. It reads a
layered JSON config, evaluates a catalogue of stable rule IDs (`MP###`, `OP###`, `SC###`,
`LC###`, `CH###`, `DP###`, `CQ###`, `LT###`, `GH###`, `MS###`, `SR###`, `SP###`, `RM###`)
against `action.yml`, the community-health surface, and live repository settings, and emits
counts, a machine-readable `id|status|message` report, and a markdown job summary.

Beyond the listed `check` surface it ships nine more composites used org-wide: `guard`,
`promote`, `name-check`, `branding-preview`, `dist-check`, `lint`, `branch-protection`,
`repo-metadata`, `relevance-gate`. Verified consumers are reusable workflows in
`blackoutsecure/bos-automation-hub`: `bos-universal-marketplace.yml` (`check`, `name-check`,
`branding-preview`), `bos-universal-security.yml` and `lint.yml` (`lint`),
`marketplace-repo-guard.yml` (`guard`), `release-promote.yml` (`promote`).

Tech stack: Python 3.10+ (`requires-python = ">=3.10"`), Hatchling build, distribution
`bos-marketplace-kit` `0.2.0`, console script `marketplace-kit`. `PyYAML>=6.0.3` is the only
runtime dependency; the config resolver, AI layer, licence audit, and relevance scorer are
stdlib-only so composites run `src/` straight off a runner with no install. Dev extras:
`pytest>=9.1.1`, `ruff>=0.16.4`, `pyyaml`, `tomli` on Python < 3.11. The root `action.yml`
is `runs.using: composite`, a thin bash-and-Python delegate forwarding all ~55 inputs to
`.github/actions/check`.

## Commands

Dev setup, then the CLI — the offline mirror of the `check` composite:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
marketplace-kit check --fail-on-warning --skip OP003,SC002   # MP/OP/SC rules
marketplace-kit doctor                      # manifest + community health + branches
marketplace-kit config --json               # resolved config cascade + provenance
marketplace-kit explain --no-ai             # deterministic remediation only
marketplace-kit doc-inputs --action-yml .github/actions/guard/action.yml
```

Tests and the lint/drift gates:

```bash
pytest                                      # testpaths=test, addopts=-ra, pythonpath=src
pytest test/test_config.py                  # one file
pytest test/test_config.py::test_marketplace_config_can_be_forced_on -q   # one test
ruff check src test scripts
python3 scripts/render_readme_inputs.py --check   # README drift; --write to fix
shellcheck -S error .github/actions/_lib/lib.sh .github/actions/*/run.sh scripts/*.sh
yamllint -c .yamllint.yml .
```

The composites need a runner (`$GITHUB_ACTION_PATH`) and are not runnable end to end
locally; `python3 .github/actions/check/scan_sc001.py <files>` runs the `SC001` scan alone.

## Validating changes

CI is driven by hub-managed kickers, not per-repo test workflows. This repository ships only
`.github/workflows/bos-universal-gatekeeper-kicker.yml` (the single dispatch front door into
the hub's reusable release, security, sync, action-test, metadata, and Marketplace
pipelines) and `.github/workflows/scorecard.yml`. The lint and documentation drift gates
therefore live inside `pytest` — see the docstring of `test/test_readme.py`.

Run narrowest first: `pytest test/<the-file-you-touched>.py`, then the full `pytest`, then
`ruff check src test scripts` and `render_readme_inputs.py --check` if you skipped the dev
extras. The suite proves every composite `action.yml` parses, declares
`runs.using: composite`, and documents every input and output; every bash `run:` body passes
`bash -n` and `shellcheck -S error`; the README generated tables, section order, table of
contents, and `OP005` size bounds hold; `src`/`test`/`scripts` are `ruff`-clean; and the
bundled metadata fallback matches `pyproject.toml`. The `shellcheck` and `ruff` assertions
skip silently when those tools are absent.

It proves nothing about runtime behaviour: no composite runs on a real runner, no GitHub
API call, no AI provider, no promote or tag push. Changes to `promote`, `guard`,
`branch-protection`, or `repo-metadata` need a real dispatch through the hub kicker.

## Architecture

```text
action.yml                  Listed Marketplace manifest; pure delegate to actions/check
docs/RULES.md               Full rule catalogue, one section per rule ID
src/marketplace_kit/
  cli.py                    argparse entrypoint; every `marketplace-kit` subcommand
  config.py                 Layered JSON config resolver; also a runnable script
  metadata.py               Package identity, deliberately separate from policy
  summary.py                Job-summary entrypoint for the check composite's AI step
  ai.py                     Optional GitHub Models / OpenAI-compatible provider layer
  licensing.py              LC### licence audit (read-only, offline)
  license_authoring.py      LICENSE/NOTICE generation and copyright merging
  osi_catalogue.py          Shared SPDX/OSI resolver; synced from the hub, do not edit
  relevance.py              Deterministic path-weighted auto-publish scoring
  data/                     Built-in marketplace config, osi-licenses.json, policies/.github/actions/
  _lib/lib.sh               Shared bash helpers (die, validate_bool, parse_pathlist)
  check/                    Rule engine: action.yml, run.sh, extract_meta.py,
                            scan_sc001.py, audit_license.py
  guard/                    PR-time publish-surface gate
  promote/                  dev -> main allowlist wipe-and-replay, tag, push
  name-check/               Marketplace name uniqueness and reserved-word checks
  branding-preview/         Renders the Feather icon + colour card as SVG
  dist-check/               Bundled dist/ freshness for JS actions
  lint/                     markdownlint-cli2 / yamllint / shellcheck / actionlint
  branch-protection/        action.yml + _bp.py drift detection and enforcement
  repo-metadata/            action.yml + run.sh + helper.py — About-box sync
  relevance-gate/           action.yml + run.sh — auto-publish scoring gate
scripts/                    Operator `gh` one-shots + the README table renderer
test/                       pytest suite; conftest.py loads composite-local helpers by path
```

A `check` run installs and SHA-verifies `actionlint`, runs `src/marketplace_kit/config.py`
to merge the config cascade into `$GITHUB_ENV`, runs `bash run.sh` to evaluate every rule
into an `ID|STATUS|MESSAGE` report, then runs `src/marketplace_kit/summary.py` to append
remediation to `$GITHUB_STEP_SUMMARY`. That last step is `if: always()` and always exits
`0`; a model is never on the critical path.

Config precedence, each tier overriding the one above: runtime defaults in `config.py` ->
built-in `data/marketplace-kit-marketplace-config.json` -> optional
`.github/marketplace-kit-global-config.json` -> the first existing file in
`REPO_CONFIG_CANDIDATES` (`.github/bos-universal-config.json` first) -> any non-empty
workflow input. Policy lives under the `marketplace_kit` section; a bad enum, a negative
length, or a path escaping the repo fails the step with exit code `2`.
Rule IDs are a two-letter family prefix plus three digits, stable across minor versions and
never reused. Per `docs/RULES.md`, adding a rule means: implement it in
`.github/actions/check` (in practice `run.sh`), document it in `docs/RULES.md` under a new
stable ID, add a `test/` case for the failure path, and bump the minor version. Severity is
`fail`/`warn`/`skip` via the matching `require_*` input or config key; `skip_checks` takes
comma-separated IDs matching `^[A-Z]{2}[0-9]{3}$`. Root action contract: ~55 optional
inputs, all defaulting to `""` (or `auto` for `use_marketplace_config`, `use_global_config`,
`workflow_dir`), meaning "fall through to the cascade"; outputs `passed`, `failed`,
`warnings`, `report`; exit `0` when everything passes or only warns, `1` on a failure or a
warning with `fail_on_warning`, `2` on a config error.

## Conventions

- Python: `from __future__ import annotations` first, a module docstring explaining the
  "why", `NamedTuple` for small result records, PEP 604 unions. `ruff` with
  `line-length = 100`, `select = ["E", "F", "W", "I", "UP", "B", "C4"]`, `ignore = ["E501"]`.
  CLI errors go to `sys.stderr` and `raise SystemExit(2)`; rule outcomes are data
  (`CheckResult(rule_id, status, message)`), not exceptions.
- Bash: `set -euo pipefail`, source `_lib/lib.sh` via `${GITHUB_ACTION_PATH}`, and fail
  through `die` so every hard error becomes a GitHub annotation:

  ```bash
  # die "<message>"  — emit GH-annotated error and exit 1.
  die() {
    printf '::error title=%s::%s\n' "${ERR_TITLE:-Marketplace}" "$*" >&2
    exit 1
  }
  ```

- Never interpolate `${{ inputs.* }}` or `${{ github.event.* }}` inside a `run:` body —
  that is exactly what `SC001` fails. Pass values through the step's `env:` block instead.
- Composite-local helpers (`branch-protection/_bp.py`, `repo-metadata/helper.py`) stay next
  to their `action.yml` so consumers pinning the sub-path get them without a `pip install`.
- Network- and AI-dependent paths must degrade to a deterministic local result. Verdicts
  stay offline: the OSI catalogue is the vendored `data/osi-licenses.json` snapshot, never a
  runtime HTTP call. Only licence authoring may reach the network.

## Blackout Secure conventions

These apply to every repository in the `blackoutsecure` organization.

### Branch model

- `dev` is the default branch and where all work lands.
- `main` is the promoted stable runtime that consumers reference through `@main`. The hub's
  reusable workflows pin this repository's composites by commit SHA plus version comment.
- Version tags (`vX.Y.Z` and a floating `vX`) point at promoted runtime commits; this
  repository is on the `v0.1.x` line with a floating `v1` tag.
- Promotion is driven from `bos-automation-hub` (`release-promote.yml`), which calls this
  repository's own `promote` composite. Do not push to `main` or move tags by hand.

### Centrally managed files - do not hand-edit here

`blackoutsecure/bos-automation-hub` distributes these through
`bos-managed-file-sync-action`. Change the source under the hub's `sync-files/`, never the
copy in this repository:

- `LICENSE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`
- `.github/FUNDING.yml`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/`
- `.github/workflows/bos-universal-gatekeeper-kicker.yml`
- the `# >>> managed-file-sync:<service> >>> ... # <<< managed-file-sync:<service> <<<`
  delimited blocks inside `.editorconfig`, `.markdownlint.yaml`, `.shellcheckrc`,
  `.yamllint.yml`, `.gitignore`, and `README.md`

Here only `LICENSE` and the kicker exist as whole managed files, the community-health files
being inherited from the org `.github` repository; marker blocks are currently present in
`.editorconfig`, `.gitattributes`, `.gitignore`, `.shellcheckrc`, `.yamllint.yml`, and
`.github/dependabot.yml`. Enabled services are listed under `managed_file_sync.services` in
the repo-owned `.github/bos-universal-config.json`, which holds this repository's overrides
on top of the hub's global config and is where gate behaviour is changed.

### CI gate

Pushes and pull requests run the hub's reusable `bos-universal-security.yml`, reported as a
single required check. It runs markdownlint, yamllint, shellcheck, and actionlint; ESLint,
Prettier, Ruff, pytest, and Bats where the repository has them; `bos-code-scanning-kit`
(secret scan, SAST, GHAS posture) and CodeQL; dependency review; and compliance checks for
the canonical README header and a conventional-commit PR title
(`feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert: subject`).

That workflow calls this repository's own `lint` composite, and this repository sets
`"defer_to_code_scanning_kit": true` so the overlapping `GH###`/`MS001` rules are owned by
`bos-code-scanning-kit`. Every `uses:` reference in a workflow must be a commit SHA with a
trailing version comment, for example `actions/checkout@<sha> # v4.2.2`.

## Boundaries

### Always

- Run `pytest` before finishing, and keep `bash -n` and `shellcheck -S error` clean on every
  composite `run:` body.
- Regenerate the README tables after touching `action.yml`.
- Give each new rule a fresh stable ID, a `docs/RULES.md` section, and a failing-case test.
- Keep the config cascade order intact, and keep AI and network calls opportunistic with a
  local fallback.

### Ask first

- Changing the root action's input or output contract.
- Adding a runtime dependency beyond `PyYAML`.
- Changing a rule's default severity, the built-in
  `data/marketplace-kit-marketplace-config.json`, or the `strict` profile.
- Altering `promote`'s allowlist semantics, denylist, or tag behaviour.
- Anything that changes published behaviour for `@v1` consumers.

### Never

- Never commit secrets, tokens, PATs, or key material.
- Never hand-edit managed-file-sync blocks, `osi_catalogue.py`, or `data/osi-licenses.json`
  here; edit the hub source instead.
- Never add an unpinned `uses:` ref or a third-party action to `.github/actions/**`.
- Never push to `main` or move an existing tag by hand.
- Never interpolate untrusted input into a `run:` block.
- Never weaken `SC001`/`SC002`, `promote`'s workflow hard-block, or branch protection.
- Never commit generated artifacts or caches.
