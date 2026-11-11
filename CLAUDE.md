# Notes for Claude

Project: home art/photo frame on a Samsung EM32DX colour e-paper panel
(Spectra 6, 2560×1440). Stock firmware, controlled over MDC; the panel pulls
`content.json` + image from our server. Server = Home Assistant add-on.

- Docs are in Polish (`docs/`), code, identifiers and comments in English.
- The plan and its checkboxes live in `docs/PLAN.md`; keep them current.
  Device findings go into `docs/EXPERIMENTS.md` (results table) and
  `docs/DEVICE_PROTOCOL.md`.

## Server (`server/`, Python, uv)

```bash
cd server
uv sync
uv run pytest -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src
```

- `device/` MDC client (one session at a time, ~0.3 s between commands),
  manifest builder, WoL. Tests use a fake TLS panel (`tests/fake_panel.py`).
- `imaging/` pipeline: linear light + OKLab, tone map, hull-based gamut
  mapping, numba error diffusion. Dither against *perceived* ink colours,
  write *device* (nominal) colours. Spectra 6 yellow is lighter than white:
  use `Palette.white_index()` / `neutral_range()`, never "lightest ink".
- `web/app.py` FastAPI: `/panel/*` for the panel (no auth, must never 404
  once content exists), `/api/*` for the app (Bearer token).
- Never hand-edit `uv.lock`; use `uv add` / `uv lock`.
- The rules that decide which works are shown and which are one work are
  being made one (`docs/RULES.md`, the audit of 2026-11-11 and its plan).
  What every place answers about every kind of work is frozen in
  `tests/test_rules_matrix.py`: a change of a rule that moves a mark there
  is a change of what the owner sees, his to decide.
  Whether a work is shown (or taken on) somewhere is asked of
  `library/verdict.py`: `against(item, Place.X, asked)`, with what each
  place minds in its `MINDS` table. Never put `vocabulary`'s `is_detail`,
  `is_postal`… together anew at a call site; a new reason is a new `Why`.
  The order in which the server proposes works (Odkrywaj's themes,
  Propozycje dnia) is `library/good.py` (`Library.query(sort="good",
  seed=day)`): a changed weight there changes what he sees, too.
- Museum requests go through `library/hosts.py` with the rules in
  `library/policy.py`. Search pages are kept on disk for days and survive
  releases: when you change how one museum's answers become `Item`s, raise
  its number in `library/pages.py` `READINGS` so its pages are asked again.

## iOS (`ios/`)

XcodeGen (`project.yml`); the `.xcodeproj` and `Info.plist` are generated and
git-ignored. iOS 26+, SwiftUI, `@Observable`, Liquid Glass. CI builds and tests on macOS
(`.github/workflows/ios.yml`): it is the only compile check when working
from Linux.
Screenshots are not part of CI: when a branch changes the look, dispatch
`ios-screenshots.yml` on that branch (`workflow_dispatch`, ref = branch) and
take the `screenshots` artifact (input `only`: a regex of shot names, e.g.
`^confirm-`, to capture just those).
`.confirmationDialog` goes on the button (or menu, or card) that asks, never
on a page or section: on iOS 26 it is a popover pointing at that view.
Pages: `.paperPage()` on the ScrollView (never a bare `.background(Theme.paper)`,
`PageLayoutTests` fails on it) and `.pageWidth()` on its content. A vertical
ScrollView is only as wide as its content, so a page holding just a spinner or
an empty list was a narrow beige strip on white (`Design/Page.swift`).

## CI

Workflows run on branch pushes only (no `pull_request` trigger; a PR shows
the push checks). On `main` only `testflight` and `publish` (plus `server`)
run. `publish` on a non-main branch tags only `sha-<commit>`, never `latest`.

## Deployment

One image, two ways to run it (the user decides later): HA add-on on HA Green
(aarch64, `ha-addon/`) or a plain container on Synology next to HA Container
(amd64, `deploy/synology/docker-compose.yml`, image `ghcr.io/artrybka/frame`
published by `.github/workflows/publish.yml` on `main`).

## Add-on (`ha-addon/`)

Debian-based (numba has no musl wheels). `scripts/bundle-addon.sh` copies
`server/` in for local/CI builds; otherwise the Dockerfile installs from git.
Bump `version` in `ha-addon/config.yaml` and `CHANGELOG.md` on release.
