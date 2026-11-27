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
  mapping, numba error diffusion. The panel dithers the picture itself
  (passthrough, JPEG); only the mat and its bevels are dithered here, to
  pure inks. Dither against *perceived* ink colours, write *device*
  (nominal) colours. Spectra 6 yellow is lighter than white:
  use `Palette.white_index()` / `neutral_range()`, never "lightest ink".
  When what the scan's merging (`imaging/reflections.py`, `imaging/glare.py`)
  makes of the same photographs changes, raise `MERGING` in `own_works.py`:
  his works scanned in the last two weeks are then made again from their
  kept photographs after the update. Raise `PhoneScan.merging` in the app
  with it once the core merges the same (`tests/test_scan_core.py` holds
  the two): the phone says it with every scan, and a scan made by an app
  that says less is made again on the server after its next start.
  A work of his own is kept without its lens's bend (`imaging/lens.py`):
  only a lens that was measured (`BENDS`, by the photograph's EXIF model),
  and only when the work is added or made again. The waiting photograph
  and a scan's kept ones stay as taken: the phone shows its own copy and
  the corners are set on that (a kept scan notes `lens` and `straight`).
  The app sends the camera's own table of how its lens bent a scan's
  first photograph (`AVCameraCalibrationData`, `OwnLens`; Mateusz
  2026-11-19): the work is straightened by that where it says what
  `BENDS` says of the lens (`lens.chosen`, within `AGREES`), by the
  measured number where it does not. Of a lens not measured the table is
  noted and not gone by while `ALONE` is false: set it only once his own
  scans' log lines ("the camera's table says …") have shown the two
  agree. A work made again is straightened by what its scan noted
  (`straight`: the number or the table), never by another.
  Where the server says what the bend is (`Incoming.straight`), the phone
  takes it out itself (Mateusz 2026-11-19 09:52 UTC: "Czy tego także nie
  lepiej robić na iPhone?"): of what it shows him (`OwnPicture.straight`;
  the corners he sets on that go on as they are on the photograph taken,
  `lens.bent`: corners in `/api/own/*` are always on the photograph as
  taken) and of the scan it made (`/merged` with `straight`). Such a scan
  waits straightened (`STRAIGHT` beside it) and the work is added from it
  as it came; whatever puts a photograph as taken back in its place
  (`single`, a merge here) takes the mark away. The scan's kept
  photographs stay as taken. `lens.straight`, `moved` and `bent` are
  written a second time in the core (`core/scan/src/scan_lens.cpp`): a
  change of one is a change of the other, checked with
  `core/scan/tools/lens.py` and held by the fixture in
  `PhoneScanTests.swift` (`tests/test_scan_core.py`).
  The merge of a scan (`imaging/reflections.py`) is written a second time
  in C++ for the phone (`core/scan`), and the phone makes his scans with
  it (`ios/…/PhoneScan.swift`, sent to `POST /api/own/photos/{token}/merged`;
  Mateusz 2026-11-19). The server's merge is the spare: a scan with no
  corners found, whatever the phone could not make or send, and his kept
  scans made again. Nothing is merged on both to be compared. A colour
  chart beside the work is read here (`imaging/colorchecker.py`), and the
  phone puts its own photographs in its colours before it merges them, by
  what `colorchecker.tables` gives it (`GET /api/own/photos/{token}/chart`,
  `core/scan/src/scan_chart.cpp`): what `_put` goes by is to be in those
  tables, and their head (`TABLES`) is raised when they change (a core
  that knows another head leaves the scan to the server).
  The Python here stays the truth. Its numbers reach the
  core through `core/scan/tools/constants.py` (`tests/test_scan_core.py`
  fails until `constants.hpp` is made again); a changed step of the merge
  is changed in the core by hand, and checked step by step on a kept scan
  with `tools/golden.py` and `tools/check` (his scans never go into the
  repo; `tools/chart.py` and `tools/chart` for the chart's colours). The
  same test holds the phone's own rules to the server's (which side
  photographs, how small, what corners; `PhoneScan`'s numbers), its
  reading of a photograph to `load_image`'s and its putting of a chart's
  colours to `colorchecker.apply`'s (a made-up file and a made-up chart
  gone through by both, `ios/FrameTests/PhoneScanTests.swift`).
  Museum photographs are cut by a model on the phone, with no Claude
  (Mateusz 2026-11-20; `AiConfig.crops_on_phone`): the app's Core ML model
  (`ios/Models/Kadr.mlpackage`, trained on the Mac) gives the masks, and
  what is made of them is `imaging/crop_model.py`, written a second time in
  the core (`core/scan/src/scan_crop.cpp`, checked with `tools/crop.py`;
  its numbers through `tools/constants.py`; the app's numbers and a fixture
  held by `tests/test_scan_core.py`). A new model is a new `MODEL` (both
  sides): its works are looked at again. A print's sheet is cut down
  round its impression where the paper is wide (`crop_model.plate`, the
  core's `frame_crop_plate`, checked with `tools/crop.py … plates`): a
  change of it raises `PLATE`, and the prints cut before are cut again
  once. A print the model left whole or unsure is cut where its paper
  bears it out (`crop_model.sheet_cut`, the app's `MuseumCrop.sheetCut`),
  and the margin is round the impression with its lettering: a cut never
  goes through anything printed or written. `phone_crops.py` keeps what the phone found, the owner's list
  "Kadrowane" and the lessons for retraining. The server has the same
  weights in ONNX (`imaging/models/kadr-*.onnx`, `crop_night.py`) and
  looks at night at what the phone has not (Mateusz 2026-11-24, „Na
  serwerze w nocy”): a new model is exported there too (its name and the
  app's weights are held by `tests/test_scan_core.py`).
- Our restorer (ArtSR, `restorer.py`) runs on the phone by itself when a
  card of a small picture opens (Mateusz 2026-11-27: „Wszystko.”;
  `PhoneRestorer`, `ios/Models/ArtSR.mlpackage`): `descreen.descreened`
  before the model and `restorer.fit`, `recoloured` and `_laid` after are
  written a second time in the core (`core/scan/src/scan_restore.cpp`,
  checked with `tools/restore.py`; numbers through `tools/constants.py`,
  the app's held by `tests/test_scan_core.py`): a change of one is a change
  of the other. The server keeps what the phone sends (`/restore/drawn`)
  and still draws what it is asked to (Pro, a playlist's batch). Only
  Google's drawing ("Restauracja", `SharperCopy.pro`) is marked, listed in
  "Restaurator" and switched before/after; our model's (`plain`) is shown
  as the picture was, its low-resolution mark by `SharperCopy.before`
  (Mateusz 2026-11-27).
- "Barwy" in "Podobne do" (`library/palettes.py`): works by their bars'
  palettes. A photograph's palette is made on the phone the same way
  (`ios/…/PhonePalette.swift`); `tests/test_palettes.py` holds the two
  (constants and the fixture rows in `PhonePaletteTests.swift`).
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
Galeria's ways between the whole screen and the grid are looked at on film
before a release: `only: gallery-probe` (a finger on the simulator,
`FrameUITests/GalleryProbeTests.swift`; the artifact has the `.mov`, the
app's `GalleryLog` and the steps' times). The grid's tiles lie where
`GridMetrics` says and are cut as their pages are (`Fill`, `closer`): keep
the two one picture, or the way between them jumps again. A page born
under the grid starts with its tile's picture, and the point a work is cut
about is whichever of the two found one first (`GridStock.focus`). The
camera's zooms are one geometry effect ignored by layout (`Seen`): with
`scaleEffect` and `offset` the pages' scroll view took safe-area insets
while it lay near the screen's edges and was scrolled out of place. The
probe's logs trace every frame of a way (`-galleryTrace YES`): read them
beside the film, which drops frames. A work's thumbnail and full picture
are one cut: Galeria asks for both by the picture's version
(`GalleryView.thumb(of:)`, `Item.originalRef`) and drops its stock when a
work is cut down (`taken`); a page looked at never changes its picture
(`GalleryPage`'s `Recut`), and two pictures of different shapes are never
laid out as one (`arrived`). The point a work is cut about
(`SubjectFocus`, `subject: true`): of a subject much wider than the screen
it is the part Vision's attention map is heaviest in (`telling`), not the
middle of its box (Mateusz 2026-11-26). The simulator on CI gives one and
the same map for every picture: what Vision finds in a work is asked of
the runner's own Mac (a Swift script run with `swift`), never of a test.
`.confirmationDialog` goes on the button (or menu, or card) that asks, never
on a page or section: on iOS 26 it is a popover pointing at that view.
Polish line breaking (no "i", "w" left at a line's end, `Design/Typography.swift`):
show text with `Text(bound: value)`, also a sentence written in the code
(`Text(bound: "…")`; SwiftUI's `Text("…")` cannot be bound from one place),
and `value.bound` for a `Label`, `Button`… Never a bare `Text(value)`. Only on what is shown, never on what is
typed, edited, searched or sent. The frame's "Opis" page does the same on the
server (`imaging/breaks.py`); keep the two rule sets in step.
`ios/Vendor/Scan` (the scan's core and OpenCV, static) is built by
`scripts/build-scan.sh` like `Vendor/Tailscale`; CI keeps both in its cache
(`.github/actions/scan-core`), and building OpenCV anew takes some twenty
minutes: raise `BUILD` in `build-opencv.sh` only when its options change.
OpenCV is built there without `-ffast-math` and with `-ffp-contract=off`
(its own iOS build sets the first; with either, the phone's scan was a
level off the server's in 8% of its numbers): never take them back out.
Pages: `.paperPage()` on the ScrollView (never a bare `.background(Theme.paper)`,
`PageLayoutTests` fails on it) and `.pageWidth()` on its content. A vertical
ScrollView is only as wide as its content, so a page holding just a spinner or
an empty list was a narrow beige strip on white (`Design/Page.swift`).

## CI

Workflows run on branch pushes only (no `pull_request` trigger; a PR shows
the push checks). On `main` only `testflight` and `publish` (plus `server`)
run. `server` runs its tests in parallel (`pytest -n auto`, so a test must not
lean on another's files or timing) and skips a merge into `main` whose
`server/` is the merged branch's, already passed there.
`publish` on a non-main branch tags only `sha-<commit>`, never `latest`.

## Deployment

One image, two ways to run it (the user decides later): HA add-on on HA Green
(aarch64, `ha-addon/`) or a plain container on Synology next to HA Container
(amd64, `deploy/synology/docker-compose.yml`, image `ghcr.io/artrybka/frame`
published by `.github/workflows/publish.yml` on `main`).

## Add-on (`ha-addon/`)

Debian-based (numba has no musl wheels). `scripts/bundle-addon.sh` copies
`server/` in for local/CI builds; otherwise the Dockerfile installs from git.
Bump `version` in `ha-addon/config.yaml` and `CHANGELOG.md` on release.
