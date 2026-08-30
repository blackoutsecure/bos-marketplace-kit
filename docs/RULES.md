# Check rule catalogue

**Copyright © 2025-2026 Blackout Secure | Apache License 2.0**

The full rule reference for [`bos-marketplace-kit`](../README.md).
Split out of the README because the rendered README has a hard size
ceiling (`OP005`), and this catalogue is the bulk of it.

The `check` action enforces a layered set of rules against your
`action.yml`. Each rule has a stable ID across versions; skip
individual rules with the `skip_checks` input.

Rule families:

| Prefix  | Severity     | Failure causes                                                                                                                                                                                                |
| ------- | ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `MP###` | **Fatal**    | Marketplace publish prerequisite missing or invalid. Action would not be acceptable to GitHub.                                                                                                                |
| `OP###` | Warning      | Best-practice violation. Non-fatal by default; set `fail_on_warning: true` to promote.                                                                                                                        |
| `SC###` | **Fatal**    | Security-impacting default missing. Failure indicates a supply-chain or token-exposure risk.                                                                                                                  |
| `LC###` | Configurable | Licence audit — SPDX resolution, OSI approval and standing, drift across README/`pyproject.toml`/`package.json`, copyright notice, Apache `NOTICE`. Default `warn`; set `require_license_audit`.              |
| `CH###` | Configurable | Community-health file missing. Default `warn` or `skip` per file; promote to `fail` via the matching `require_*` input.                                                                                       |
| `DP###` | Configurable | Dependabot config missing. Default `warn`.                                                                                                                                                                    |
| `CQ###` | Configurable | CodeQL workflow missing. Default `warn`.                                                                                                                                                                      |
| `LT###` | Configurable | Lint config file missing (`.editorconfig`, `.gitattributes`, `.gitignore`, markdownlint, yamllint).                                                                                                           |
| `GH###` | Configurable | GitHub Advanced Security toggle disabled (code scanning, secret scanning, Dependabot alerts). Requires `github_token`.                                                                                        |
| `MS###` | Configurable | Microsoft Security DevOps workflow missing. Default `skip` (opt-in).                                                                                                                                          |
| `SR###` | Configurable | OpenSSF Scorecard workflow missing. Default `skip` (opt-in).                                                                                                                                                  |
| `SP###` | Configurable | GitHub Sponsors listing not approved for the account, not wired into a `FUNDING.yml` GitHub reads, or not rendering on the repo. Default `skip` (opt-in). Requires `github_token`.                            |
| `RM###` | Configurable | Live repo settings: the "About" box (description, homepage, topics) and the Issues tab. Reads `GET /repos/{owner}/{repo}` (default `GITHUB_TOKEN` is sufficient). Companion to the `repo-metadata` composite. |

## MP001 — Top-level manifest keys

**Required:** `name`, `description`, `runs` MUST be present at the
root of `action.yml`. `runs:` must be a mapping containing at least
`using:`.

## MP002 — `name` is non-empty

`name:` must be a non-empty string. Marketplace displays this on the
listing card and across search results.

## MP003 — `description` is non-empty

`description:` is the one-line subtitle on the Marketplace card. See
also: [MP010](#mp010--description-is-too-long).

## MP004 — `runs.using` is present

`runs:` must declare an execution model: `composite`, `node20` (or
newer LTS), or `docker`. Set `runs.using: composite` for most
shell-driven actions.

## MP005 — `branding.icon` is present

Marketplace requires a Feather icon name in `branding.icon`. The
icon set is pinned to Feather v4.28.0 by GitHub. Use the kit's
`branding-preview` action to render the resulting card before
pushing.

```yaml
branding:
  icon: check-circle
  color: green
```

## MP006 — `branding.color` is in the allowed enum

Allowed: `white`, `yellow`, `blue`, `green`, `orange`, `red`,
`purple`, `gray-dark`. No hex codes, no other names.

## MP007 — `action.yml` lives at the repo root

Marketplace only lists a single manifest at the root of the default
branch. Subdirectory manifests (e.g. `.github/actions/foo/action.yml`)
are permitted in the repository but are **not** listable — GitHub's docs
state "repositories may include other actions metadata files in
sub-folders, but they will not be automatically listed in the
marketplace". The `promote` action's allowlist should include
`action.yml`.

## MP008 — `LICENSE` present at the repo root

Marketplace requires a licence file. `LICENSE`, `LICENSE.md`,
`LICENSE.txt`, and `COPYING` all satisfy it. Presence is all MP008
asks; see [LC001-LC006](#lc001-lc006--licence-audit) for whether the
file actually says something coherent.

## MP009 — No workflow files on the publishing branch

Marketplace publishing requires zero files under `workflow_dir` on the
default branch. Reported as a warning here because it is expected to
fail on `dev`; the `guard` action enforces it as a hard failure at
promote time, and `promote` strips them.

## MP010 — Description is too long

`description:` must be **125 characters or fewer**. Marketplace
truncates anything past the limit in the card view, so a longer
description ships a truncated subtitle to consumers — a hard fail by
default. Tighten to a single short sentence; use `README.md` for
elaboration.

Enforced by both the `check` composite action and the
`bos-marketplace-kit` CLI; cannot be downgraded to a warning.

## OP003 — `author` is set

Optional but strongly recommended. Marketplace shows the author on
the listing card. Add `author: Your Org Name`.

## OP004 — README has a Usage / Quickstart / Example section

Marketplace consumers scan READMEs looking for a copy-pasteable
snippet. The check looks for a heading matching
`Usage`, `Quickstart`, `Getting Started`, or `Example` (any depth).
Add one to your `README.md`:

````markdown
## Usage

```yaml
- uses: your-org/your-action@v1
  with:
    foo: bar
```
````

### OP005 — README is a reasonable size

A README under 512 bytes reads as low-effort to Marketplace
consumers; one above 128 KB hits the GitHub-side render limit. The
check passes when `README.md` is between 512 B and 128 KB.

### OP006 — README contains at least one image or badge

Listings without any visual element look notably less polished. A
status badge (e.g. CI passing, version) or a single screenshot is
enough. Any markdown image syntax `![alt](url)` satisfies the rule.

### OP007 — README contains at least 3 fenced code blocks

Marketplace consumers expect copy-pasteable snippets. The check
counts triple-backtick fenced blocks (` ``` `) and warns if fewer
than 3 are present.

### SC001 — Composite actions don't interpolate user input into `run:`

When a composite action interpolates `${{ inputs.* }}` or
`${{ github.event.* }}` directly inside a `run:` block, an attacker
who controls the input value (e.g. via a PR title) can break out of
the shell context and execute arbitrary code on the runner. Plumb
untrusted values via the step's `env:` block instead, then reference
the shell variable inside the script:

```yaml
- shell: bash
  env:
    TITLE: ${{ github.event.pull_request.title }}
  run: echo "$TITLE"
```

This rule is enforced by the bundled `check` composite action (which
scans every `run:` block under `.github/actions/**`). The CLI's
equivalent SHA-pinning rule is `SC002`.

## SC002 — Third-party actions are pinned by SHA

Tag/branch refs (`@v4`, `@main`) are mutable. A compromised tag move
can inject arbitrary code into your runner. SHA pins (`@<40-hex>`)
are immutable. Use Dependabot or `bos-upstream-watcher` to bump pins
automatically.

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
```

## SC003 — Security policy is discoverable

Public Marketplace listings should advertise a private reporting
channel for security issues. The check looks for any of:

- `SECURITY.md`, `.github/SECURITY.md`, or `docs/SECURITY.md` in the
  calling repo,
- the same files in the org's `.github` repository (when
  `check_org_health: true` and a token is supplied), **or**
- a README that mentions `security policy`, `SECURITY.md`, or
  `report ... vulnerability`.

Strictness is controlled by the `require_security` input:

| Value  | Behaviour on a missing policy                                                                   |
| ------ | ----------------------------------------------------------------------------------------------- |
| `fail` | Hard failure — the README escape hatch is also disabled at this level.                          |
| `warn` | **Default.** Records a warning. The action overall still passes unless `fail_on_warning: true`. |
| `skip` | Rule short-circuits to a `skip` status — equivalent to listing `SC003` in `skip_checks`.        |

Generate a template:

```bash
marketplace-kit generate-policy security \
  --owner my-org --repo my-action --email security@example.com
```

## LC001-LC006 — Licence audit

`MP008` only proves a `LICENSE` file exists. The `LC###` family proves
it says something coherent. All six default to `warn` and move together
via `require_license_audit`.

| ID      | Passes when                                                                                                                                                                         |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `LC001` | `LICENSE`/`COPYING` resolves to a known SPDX identifier. Otherwise GitHub, npm, and consumer policy bots all read `NOASSERTION`.                                                    |
| `LC002` | The identifier is OSI-approved, off `denied_licenses`, and on `allowed_licenses` when set. Catches `BUSL-1.1`, `SSPL-1.0`, `Elastic-2.0`, NonCommercial CC, and npm's `UNLICENSED`. |
| `LC003` | The identifier is not OSI _superseded_ or _voluntarily retired_. The finding names the replacement (`EPL-1.0` → `EPL-2.0`, `MPL-1.1` → `MPL-2.0`, …).                               |
| `LC004` | Every other surface agrees — README badge, `pyproject.toml`, `package.json`. Drift is the finding that recurs; the rest are one-time fixes.                                         |
| `LC005` | A filled-in `Copyright <year> <holder>` exists in `LICENSE`, `NOTICE`, or the README header, with no template placeholder left. The Apache appendix is excluded.                    |
| `LC006` | A `NOTICE` exists when the licence is Apache-2.0 (§4(d)). Skipped otherwise.                                                                                                        |

Approval and standing resolve against a **vendored snapshot** of
[the OSI approved-licence list](https://opensource.org/licenses) at
`src/marketplace_kit/data/osi-licenses.json` — no network call, so the
verdict is reproducible offline in `marketplace-kit doctor`. Refresh it
with [`bos-upstream-watcher`][uw].

Detection is deterministic (`SPDX-License-Identifier:` header, then
licence-text patterns). AI inference is consulted **only** when that
fails, is labelled low-confidence, and can never raise a finding above
`warn`. Restrict the accepted set with `require_license_audit`,
`allowed_licenses`, and `denied_licenses`.

The snapshot and its resolver (`osi_catalogue.py`) are generated and
owned in [`bos-automation-hub`][hub] and delivered as a versioned pair by
managed file sync, so this kit and `bos-code-scanning-kit` resolve any
given licence string identically without either depending on the other.

[uw]: https://github.com/blackoutsecure/bos-upstream-watcher
[hub]: https://github.com/blackoutsecure/bos-automation-hub

Dependency licences are a separate concern, covered by `LD001`-`LD005`
and `LF001`-`LF004` in [`bos-code-scanning-kit`][csk].

### Fixing what the audit finds

`marketplace-kit license` is the write side of `LC###`. It supports every
OSI-approved identifier in the catalogue — 155 at the current snapshot,
not a hardcoded shortlist:

```bash
# What can I generate?
marketplace-kit license --list

# Create a LICENSE, filling in the copyright from what the repo already claims
marketplace-kit license --generate Apache-2.0

# Add a second holder; existing attribution is merged, never replaced
marketplace-kit license --holder "2019-2021 Acme Corp" --dry-run

# Reconcile LICENSE / NOTICE / README so LC007 passes
marketplace-kit license --fix
```

Copyright handling is the fiddly part, and is the reason this exists:
holders accumulate, each with their own years, spelled differently in
different files. Notices are merged per holder (case-insensitively) and
their years unioned and collapsed into ranges, so `2019`, `2020-2021`
and `2024` for one holder render as `2019-2021, 2024`.

Licence _text_ is not vendored — 155 full texts would bloat every
consumer for a file most repos need once — so `--generate` fetches it
from the SPDX license list when you ask. That split is deliberate:
**verdicts stay offline and reproducible; authoring may reach the
network.** Nothing in the audit path makes a request.

> **We are not lawyers, and none of this is legal advice.** The `LC###`
> rules and the `license` command are consistency and authoring tooling.
> They aim to keep your licence and copyright metadata accurate,
> complete, and machine-readable. Anything that turns on legal
> interpretation belongs with qualified counsel.

[csk]: https://github.com/blackoutsecure/bos-code-scanning-kit

## CH001-CH006 — Community-health files (org-aware)

The kit checks a small set of community-health files Marketplace
consumers expect on a popular public action. Each rule looks in this
repo first; if the file is missing, it falls back to the owner's
`.github` repository (canonical home for shared defaults) when
`check_org_health: true` and `github_token` is non-empty. That
fallback repo is `${org_health_repo}`, defaulting to
`<owner>/.github` — GitHub honours it for **personal accounts and
organizations alike**, and it must be **public** for the defaults to
apply. If found in either location the rule passes; the report
message records which location was used.

| ID    | File                                                               | Default policy | Generator kind                |
| ----- | ------------------------------------------------------------------ | -------------- | ----------------------------- |
| CH001 | `CODE_OF_CONDUCT.md` (also `.github/`, `docs/`)                    | `warn`         | `code-of-conduct`             |
| CH002 | `CONTRIBUTING.md` (also `.github/`, `docs/`)                       | `warn`         | `contributing`                |
| CH003 | `SUPPORT.md` (also `.github/`, `docs/`)                            | `skip`         | `support`                     |
| CH004 | `.github/ISSUE_TEMPLATE/` directory or `.github/ISSUE_TEMPLATE.md` | `skip`         | `issue-bug` / `issue-feature` |
| CH005 | `.github/PULL_REQUEST_TEMPLATE.md`                                 | `skip`         | `pr-template`                 |
| CH006 | `.github/FUNDING.yml` (the only path GitHub reads for funding)     | `skip`         | `funding`                     |

Each rule takes a matching `require_*` input (`require_code_of_conduct`,
`require_contributing`, `require_support`, `require_issue_templates`,
`require_pr_template`, `require_funding`) with values `fail | warn |
skip` and the same semantics as `require_security` above.

### Source mode — local vs inherited from the org `.github` repo

Each CH/SC rule additionally accepts a `*_source` input describing
_where_ the file is expected to live. This lets you express the
"don't ship CoC/SECURITY/SUPPORT in every repo; inherit them from
the org `.github` repo" pattern without losing the safety net of an
explicit check.

| Mode      | Local check | Org fallback | Pass when                                                   |
| --------- | ----------- | ------------ | ----------------------------------------------------------- |
| `local`   | yes         | **disabled** | the file exists in this repo.                               |
| `inherit` | **skipped** | yes          | the file exists in `${org_health_repo}`.                    |
| `either`  | yes         | yes          | the file exists in either location (default — back-compat). |

Two layers of inputs:

- **`community_health_source`** sets the global default (one of
  `local | inherit | either`; default `either`).
- **Per-rule overrides** — `security_source`, `code_of_conduct_source`,
  `contributing_source`, `support_source`, `issue_templates_source`,
  `pr_template_source`, `funding_source` — take precedence when
  non-empty (default empty = use global).

Worked example: the kit itself ships **none** of the seven
community-health files locally — they all live in
`blackoutsecure/.github` and inherit. A typical consumer keeps a
repo-specific `CONTRIBUTING.md` (local release flow, dev-loop
commands) and inherits the rest:

```yaml
- uses: blackoutsecure/bos-marketplace-kit@v1
  with:
    github_token: ${{ github.token }}
    require_security: warn
    require_code_of_conduct: warn
    require_contributing: warn
    require_support: warn
    require_funding: warn
    # Default everything to inherit from the org `.github` repo ...
    community_health_source: inherit
    # ... but keep the contributor guide local because it has
    # repo-specific release / dev-loop content:
    contributing_source: local
```

When a rule's source is `inherit` and the org lookup is unavailable
(token missing, `check_org_health: false`, or the probe fails), the
rule emits the configured severity with an explicit reason rather
than silently falling back. This guarantees that "inherit" never
means "silently pass".

### Org-aware lookup

Set `check_org_health: true` (default) and pass `github_token:
${{ github.token }}` to enable the fallback. The check makes one
`GET /repos/{owner}/.github` call to confirm the health repo exists,
plus one `contents/{path}` call per missing file (0-6 cheap calls per
run). Override the destination with `org_health_repo: my-org/.github`
if your account uses a non-default location.

### Generate a starter template

The kit ships a small, opinionated set of policy templates and a CLI
to emit them with placeholder substitution:

```bash
marketplace-kit generate-policy list          # available kinds
marketplace-kit generate-policy code-of-conduct \
  --owner my-org --repo my-action --email contact@example.com
marketplace-kit generate-policy contributing --stdout
```

Placeholders: `{{owner}}`, `{{repo_name}}`, `{{contact_email}}`,
`{{project_name}}`. Unsubstituted placeholders fall back to
conservative defaults (`YOUR-ORG`, CWD basename,
`security@example.com`).

### Install one (or every) recommended file

`generate-policy` is the low-level emitter. `install` is the safe
one-shot scaffolder you reach for when bootstrapping a fresh repo
— it writes to canonical paths, refuses to overwrite existing files
by default, and can install every recommended kind in one call:

```bash
# Scaffold a single kind at its canonical path. Refuses to
# overwrite an existing file — pass --force to replace it.
marketplace-kit install codeql-workflow --owner my-org

# Install every recommended community-health, supply-chain, and
# lint file that isn't already present. Existing files are left
# alone (use --force to overwrite all). Use --dry-run to preview.
marketplace-kit install --all --owner my-org

# Preview without touching anything.
marketplace-kit install --all --owner my-org --dry-run
```

What `install --all` covers: `security`, `code-of-conduct`,
`contributing`, `support`, `issue-bug`, `issue-feature`,
`pr-template`, `funding`, `dependabot`, `codeql-workflow`,
`markdownlint`, `yamllint`. Opt-in kinds (`scorecard-workflow`,
`security-devops-workflow`, `shellcheckrc`) must be installed
explicitly by name to avoid surprising consumers who don't want them.

After `install`, run `marketplace-kit check` to confirm the kit's
rules pass — the canonical pipeline is **check → install → commit →
check passes → CI green**.

### `auto_generate_missing` — reserved for a future iteration

A `auto_generate_missing: false | true` input is declared (default
`false`) to reserve the API for a future feature: when set to
`true`, missing files would be drafted by an LLM at workflow time
and opened as a PR (against this repo for `local`/`either` rules,
or against `${org_health_repo}` for `inherit`-mode rules) so policy
files stay current as guidance evolves.

This input is a forward-compatible stub today — setting `true`
emits a one-time warning and otherwise has no effect. Existing
callers don't need to change anything once the implementation lands.
The static `marketplace-kit generate-policy` command continues to
work today and is the supported way to bootstrap a file.

## DP001 / CQ001 / LT001-005 — CI / supply-chain hygiene

Adjacent to the community-health rules, the kit checks for the
standard supply-chain and lint config files a healthy Marketplace
repo should ship. These follow the same `fail | warn | skip` policy
pattern and the same generator-template story (`marketplace-kit
generate-policy <kind>`).

| ID    | File(s)                                                                 | Default policy | Generator kind                                                              |
| ----- | ----------------------------------------------------------------------- | -------------- | --------------------------------------------------------------------------- |
| DP001 | `.github/dependabot.yml` / `.dependabot.yaml`                           | `warn`         | `dependabot`                                                                |
| CQ001 | any workflow referencing `github/codeql-action`                         | `warn`         | `codeql-workflow` _or_ `code-scan-workflow` (mutually exclusive — pick one) |
| LT001 | `.editorconfig`                                                         | `warn`         | (no template; trivial)                                                      |
| LT002 | `.gitattributes`                                                        | `warn`         | (no template; repo-shaped)                                                  |
| LT003 | `.gitignore`                                                            | `warn`         | (no template; repo-shaped)                                                  |
| LT004 | `.markdownlint.yaml` / `.markdownlint-cli2.yaml` / `.markdownlint.json` | `skip`         | `markdownlint`                                                              |
| LT005 | `.yamllint.yml` / `.yamllint.yaml` / `.yamllint`                        | `skip`         | `yamllint`                                                                  |

The lint rules default to `skip` (LT004/LT005) or `warn` (LT001-003)
so legacy repos can adopt the kit without immediate cleanup. Promote
to `fail` as your repo catches up.

### CQ001 — choose ONE of `codeql-workflow` or `code-scan-workflow`

Two templates satisfy CQ001; pick exactly one. Running both doubles
CodeQL spend on every dev push (same `github/codeql-action`, same
SARIF, twice the minutes) and splits the SHA-bump source of truth
across two files.

|                                           | `codeql-workflow`                                                                        | `code-scan-workflow`                                                                                         |
| ----------------------------------------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **What ships**                            | Standalone `.github/workflows/codeql.yml` with `github/codeql-action` SHAs pinned inline | `.github/workflows/bos-universal-security-kicker.yml` that calls the hub reusable security workflow          |
| **SHA rollouts**                          | You bump SHAs in this repo on every CodeQL release                                       | One hub commit propagates to every consumer on next run                                                      |
| **Covers**                                | CodeQL only                                                                              | CodeQL **and** the `bos-code-scanning-kit@v1` composite (posture audit + actionlint / gitleaks / shellcheck) |
| **Cross-org / external use**              | Self-contained — no hub dependency                                                       | Requires read access to `blackoutsecure/bos-automation-hub`                                                  |
| **Producer-kit escape hatch**             | n/a                                                                                      | Set `enable_kit_composite: false` if this repo IS the producer of `bos-code-scanning-kit@v1`                 |
| **Advanced posture probes (PS002/PS003)** | n/a                                                                                      | Built-in preflight + `SCANNING_PAT` plumbing                                                                 |

The `marketplace-kit install` command emits a warning if you try to
scaffold one template next to an existing canonical file for the
other. The recommended migration path:

```bash
# Migrate from standalone CodeQL to the hub-reusable form:
marketplace-kit install code-scan-workflow --owner my-org
rm .github/workflows/codeql.yml                       # commit in same PR
```

Both templates produce a top-level workflow file referencing
`github/codeql-action` (the latter as a `# uses:` documentary
comment in the header), which is what CQ001 actually keys off — it
inspects workflow files at the repo's surface, not transitive
reusable callees.

## GH001-GH003 — GitHub Advanced Security toggles (live repo settings)

These rules call the GitHub API to verify your repo-level security
toggles are actually enabled — surfacing drift between intent ("we
turned on secret scanning") and reality. Each requires `github_token`
with the appropriate scope.

| ID    | Setting                                          | API                                                              | Token scope                      | Default |
| ----- | ------------------------------------------------ | ---------------------------------------------------------------- | -------------------------------- | ------- |
| GH001 | Code scanning (CodeQL default-setup OR workflow) | `GET /repos/{}/code-scanning/default-setup`                      | `metadata: read`                 | `warn`  |
| GH002 | Secret scanning                                  | `GET /repos/{}` → `security_and_analysis.secret_scanning.status` | admin/write on repo (PAT/App)†   | `warn`  |
| GH003 | Dependabot alerts                                | `GET /repos/{}/vulnerability-alerts` (204/404)                   | `Administration: read` (PAT/App) | `warn`  |

† **About GH002:** `security_and_analysis` is only present in
`GET /repos/{}` responses when the caller has admin or write access
to the repo. The default `GITHUB_TOKEN` does NOT see this field
even though it can read the rest of the repo metadata. When the
field is absent, GH002 emits `skip` with a remediation hint rather
than a false-positive `disabled` -- supply a PAT or App
installation token with admin/write to introspect.

**Public repos:** all three features are free; default-on for new
repos created after 2023 and recommended for everything else.

**Private repos:** require a GitHub Advanced Security license. Set
`require_ghas_*: skip` if you're on a plan without GHAS.

If the token lacks scope the rule emits `skip` (not `fail`) with an
explanation, so a missing `Administration: read` doesn't silently
mask the broader check.

## MS001 — Microsoft Security DevOps workflow (opt-in)

`microsoft/security-devops-action` wraps a curated set of OSS scanners
(Bandit, Checkov, ESLint, Terrascan, Trivy, BinSkim, PSRule, …) and
surfaces findings as SARIF in GHAS code-scanning. For Azure-connected
repos, findings also flow into Microsoft Defender for Cloud.

- **Default:** `skip` — high signal for repos shipping IaC or
  container images, marginal noise for pure source repos.
- **Generator:** `marketplace-kit generate-policy security-devops-workflow`.
- Set `require_security_devops: warn` (or `fail`) for IaC-heavy or
  containerised repos.

## SR001 — OpenSSF Scorecard workflow (opt-in)

`ossf/scorecard-action` scores your repo's supply-chain posture
against the OpenSSF Scorecard checks (Branch-Protection, Pinned-Deps,
Token-Permissions, etc.) and publishes the result at
<https://scorecard.dev>. Free for public repos.

- **Default:** `skip`.
- **Generator:** `marketplace-kit generate-policy scorecard-workflow`.
- Recommended for public Marketplace actions — your Scorecard becomes
  a public quality signal alongside the Marketplace listing.

## SP001-SP003 — GitHub Sponsors (opt-in)

GitHub Sponsors is approved **per account**, not per repository. Until
the account is approved and its listing is published there is no
Sponsor button, no matter what `FUNDING.yml` says — so these rules read
live state from GraphQL (`repositoryOwner { hasSponsorsListing }`,
`repository { fundingLinks }`) instead of inferring it from the repo
tree. CH006 stays the file-presence rule; SP### is the account- and
render-state rule. All three move together via `require_sponsorship`
(default `skip`) and need `github_token`.

| ID    | Pass criterion                                                                  |
| ----- | ------------------------------------------------------------------------------- |
| SP001 | The account has an approved, published GitHub Sponsors listing                  |
| SP002 | A FUNDING.yml GitHub actually reads declares `github: <login>` for that account |
| SP003 | The repo renders funding links — i.e. the Sponsor button is genuinely visible   |

The account checked is `sponsorship_account` when set, otherwise the
repository owner. Its type is detected from the API response, so an
unapproved account is told exactly where to request approval:
[personal account](https://docs.github.com/sponsors/receiving-sponsorships-through-github-sponsors/setting-up-github-sponsors-for-your-personal-account)
or
[organization](https://docs.github.com/sponsors/receiving-sponsorships-through-github-sponsors/setting-up-github-sponsors-for-your-organization).

**Where FUNDING.yml is allowed to live.** Funding is the exception to
the community-health precedence rules: GitHub reads
**`.github/FUNDING.yml` on the default branch and nowhere else** —
root and `docs/` copies are honoured for `CONTRIBUTING.md` and friends
but silently ignored for funding. The same path in the owner's
`.github` repo is the default for every repo of that account that has
none of its own. SP002 checks local first, then inherited, and flags a
misplaced root/`docs` copy so a "missing" finding is actionable.

- `<owner>/.github` works for a **personal account**
  (`<user>/.github`) exactly as for an **organization**
  (`<org>/.github`); the kit derives it from
  `github.repository_owner` and never assumes an org. It is _not_ the
  profile-README repo (`<user>/<user>`), and it must be **public** or
  GitHub ignores the defaults.
- A repo-level file **overrides** the inherited one rather than
  merging; SP002 reports which it matched (`local` / `inherited`) so
  an accidental override is visible.
- `funding_source` (or the global `community_health_source`) picks the
  search: `local`, `inherit`, or `either` (default).

**Why SP003 exists.** Settings → General → Features → **Sponsorships**
is a separate switch from the file: with it off, a valid `FUNDING.yml`
and an approved listing still render nothing. `fundingLinks` is the
rendered result, so SP003 also catches a `FUNDING.yml` that exists on
a working branch but not on the default branch.

Each rule degrades to `skip`, never `fail`, when its precondition is
missing (no token, no listing, no funding config).

## RM001-RM006 — Live repo settings (About box + Issues tab)

Validates what the public sees in the repo sidebar — the same
fields the companion [`repo-metadata`](../README.md#repo-about-box-sync-repo-metadata)
composite writes on release. Each rule reads
`GET /repos/{owner}/{repo}`; the default `GITHUB_TOKEN` is enough
(these fields are public-readable). The job summary additionally
emits a **Current repo About box** sub-section showing the actual
live values so you can confirm what consumers see without leaving
the workflow log.

| ID    | Field                | Pass criterion                                                      | Default policy | Hard rules                                                 |
| ----- | -------------------- | ------------------------------------------------------------------- | -------------- | ---------------------------------------------------------- |
| RM001 | `description` set    | Non-empty                                                           | `warn`         | —                                                          |
| RM002 | `description` length | `repo_description_min_length` ≤ len ≤ `repo_description_max_length` | `warn`         | `>repo_description_max_length` (default 350) → **fail**    |
| RM003 | `homepage`           | http(s) URL                                                         | `skip`         | Set but non-URL → **fail** (regardless of policy)          |
| RM004 | `topics` count       | 1 ≤ count ≤ 20                                                      | `warn`         | `count > 20` → **fail** (GitHub cap; regardless of policy) |
| RM005 | `topics` format      | Lowercase, `[a-z0-9-]`, ≤ 50 chars each, no leading/trailing hyphen | (inherits)     | Any malformed topic → **fail** (regardless of policy)      |
| RM006 | Issues tab           | `has_issues` is on                                                  | `warn`         | —                                                          |

**Which repo settings are audited, and which are only reported.**
Only Issues carries a Marketplace obligation — it is the support
channel consumers are sent to, and with it off the CH004 issue
templates are unreachable. Projects, Wiki, Pages, Discussions, and
Downloads are maintainer preference, so the summary prints their live
state in a **Repo home-page tabs** table without asserting anything.
Sponsorships is audited by [SP003](#sp001-sp003--github-sponsors-opt-in),
the only way to observe it. The Releases / Deployments / Packages
sidebar widgets are write-only on the REST surface, so no rule claims
to read them back.

**Why "hard fail regardless of policy" on some rules?** When values
violate GitHub's own format/cap rules, the _next_ `PATCH /repos/{}`
or `PUT /repos/{}/topics` call would be rejected — so a warning would
mask a soon-to-be broken release.

**Tuning the bounds** (per-repo overrides):

```yaml
- uses: blackoutsecure/bos-marketplace-kit/.github/actions/check@v1
  with:
    github_token: ${{ github.token }}
    # Make every RM rule blocking on the publish branch:
    require_repo_description: "fail"
    require_repo_homepage: "fail"
    require_repo_topics: "fail"
    require_repo_issues: "fail"
    # Allow shorter "tagline-style" descriptions:
    repo_description_min_length: "0"
```

**Default `GITHUB_TOKEN` is enough** for RM001-RM006 — unlike the
`repo-metadata` composite which _writes_ these fields and needs
`Administration: write`, the check action only _reads_ them, which
`metadata: read` already covers.

## Adding new rules

Open a PR against `dev` that:

1. Adds the rule to `.github/actions/check/action.yml`.
2. Documents it in the [Check rule catalogue](#check-rule-catalogue)
   section above with a stable ID.
3. Adds a unit test under `test/` covering the failure case.
4. Bumps the kit's minor version.

The kit promises stability for `MP###`/`OP###`/`SC###`/`CH###` rule
IDs across minor versions — adding a rule never reuses an existing
ID.
