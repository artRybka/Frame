"""Colour calibration from the app: chart on the frame, photo, measured palette."""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from ..fsutil import own_dirs
from ..imaging import Palette
from ..imaging.calibrate import CalibrationError, measure
from ..imaging.palette import RGB, SPECTRA6
from ..imaging.pipeline import encode_image, render
from ..imaging.testchart import palette_chart
from ..player import Hold, utcnow
from ..service import FrameService
from .deps import require_owner, service

router = APIRouter(
    prefix="/api/calibration", dependencies=[Depends(require_owner)], tags=["calibration"]
)
Svc = Annotated[FrameService, Depends(service)]

CHART_MINUTES = 30  # long enough to take the photo; the rotation resumes after
KEEP_CANDIDATES = 5
_CANDIDATE_ID = re.compile(r"^[0-9a-f]{12}$")


class InkView(BaseModel):
    name: str
    device: RGB
    perceived: RGB


class PaletteView(BaseModel):
    name: str
    source: str
    colors: list[InkView]

    @classmethod
    def of(cls, palette: Palette) -> PaletteView:
        return cls(
            name=palette.name,
            source=palette.source,
            colors=[
                InkView(name=c.name, device=c.device, perceived=c.perceived) for c in palette.colors
            ],
        )


class CalibrationView(BaseModel):
    palette: PaletteView
    calibrated: bool  # measured in the app (otherwise the default palette)


class MeasuredInk(BaseModel):
    name: str
    device: RGB
    perceived: RGB  # the new value
    previous: RGB  # the palette in use now
    spread: float


class MeasureResponse(BaseModel):
    candidate_id: str
    inks: list[MeasuredInk]
    warnings: list[str]
    chart_url: str  # the straightened photo with the sampled areas marked


class ApplyRequest(BaseModel):
    candidate_id: str


def _view(svc: FrameService) -> CalibrationView:
    return CalibrationView(
        palette=PaletteView.of(svc.palette), calibrated=svc.calibrated_palette_path.is_file()
    )


def _candidates(svc: FrameService) -> Path:
    return svc.settings.data_dir / "calibration"


def _candidate(svc: FrameService, candidate_id: str) -> Path:
    path = _candidates(svc) / candidate_id
    if not _CANDIDATE_ID.match(candidate_id) or not path.is_dir():
        raise HTTPException(404, "unknown calibration")
    return path


def _prune(directory: Path, keep: int) -> None:
    runs = sorted(
        (p for p in own_dirs(directory) if _CANDIDATE_ID.match(p.name)),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in runs[keep:]:
        shutil.rmtree(old, ignore_errors=True)


@router.get("", response_model=CalibrationView)
def calibration(svc: Svc) -> CalibrationView:
    return _view(svc)


@router.post("/chart", status_code=202)
async def show_chart(svc: Svc) -> dict[str, Any]:
    """Put the palette chart on the frame and keep it there for a while."""
    chart = palette_chart(svc.palette)
    hold = Hold(until=(utcnow() + timedelta(minutes=CHART_MINUTES)).isoformat(timespec="seconds"))
    svc.background(
        svc.player.show_still(
            encode_image(chart, "png"),
            preview_png=encode_image(chart.resize((1280, 720)), "png"),
            title="Plansza kalibracji",
            description="Zrób zdjęcie ramki w aplikacji Frame.",
            hold=hold,
        )
    )
    return {"accepted": True, "hold_until": hold.until}


@router.post("/measure", response_model=MeasureResponse)
async def measure_photo(
    svc: Svc,
    file: Annotated[UploadFile, File()],
    corners: Annotated[str, Form(description="[[x, y] × 4]: TL, TR, BR, BL, 0–1")],
) -> MeasureResponse:
    try:
        points = [(float(x), float(y)) for x, y in json.loads(corners)]
    except (ValueError, TypeError) as err:
        raise HTTPException(422, "corners: four [x, y] pairs") from err
    data = await file.read()
    palette = svc.palette
    try:
        result = await run_in_threadpool(measure, data, points, palette, SPECTRA6)
    except CalibrationError as err:
        raise HTTPException(422, str(err)) from err
    except OSError as err:
        raise HTTPException(422, "Nie udało się odczytać zdjęcia.") from err

    candidate_id = uuid.uuid4().hex[:12]
    directory = _candidates(svc) / candidate_id
    directory.mkdir(parents=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    result.palette(
        palette,
        name=f"em32dx-{candidate_id[:6]}",
        source=f"Kalibracja ze zdjęcia w aplikacji Frame, {stamp}",
    ).save(directory / "palette.json")
    result.chart.save(directory / "chart.jpg", quality=85)
    _prune(_candidates(svc), KEEP_CANDIDATES)

    previous = {c.name: c.perceived for c in palette.colors}
    return MeasureResponse(
        candidate_id=candidate_id,
        inks=[
            MeasuredInk(
                name=ink.name,
                device=ink.device,
                perceived=ink.perceived,
                previous=previous[ink.name],
                spread=ink.spread,
            )
            for ink in result.inks
        ],
        warnings=result.warnings,
        chart_url=f"/api/calibration/candidates/{candidate_id}/chart.jpg",
    )


@router.get("/candidates/{candidate_id}/chart.jpg")
def candidate_chart(candidate_id: str, svc: Svc) -> FileResponse:
    return FileResponse(_candidate(svc, candidate_id) / "chart.jpg", media_type="image/jpeg")


@router.get("/candidates/{candidate_id}/preview/{item_id}")
async def candidate_preview(candidate_id: str, item_id: str, svc: Svc) -> FileResponse:
    """A library item on the panel with the measured palette, to compare."""
    directory = _candidate(svc, candidate_id)
    item = svc.library.get(item_id)
    if item is None:
        raise HTTPException(404, "no such item")
    path = directory / f"preview-{item.file_stem}.png"
    if not path.is_file():
        palette = Palette.load(directory / "palette.json")
        settings = svc.player.render_settings(item, svc.player.settings)
        source = await run_in_threadpool(svc.images.ensure_image, item)

        def build() -> None:
            img = render(source, settings, palette).preview_image()
            img.thumbnail((1280, 1280))
            path.write_bytes(encode_image(img, "png"))

        await run_in_threadpool(build)
    return FileResponse(path, media_type="image/png")


@router.post("/apply", response_model=CalibrationView)
async def apply(request: ApplyRequest, svc: Svc) -> CalibrationView:
    """Use the measured palette from now on and redraw the frame with it."""
    directory = _candidate(svc, request.candidate_id)
    try:
        palette = Palette.load(directory / "palette.json")
    except (OSError, ValueError, KeyError, ValidationError) as err:
        raise HTTPException(422, f"unreadable palette: {err}") from err
    svc.set_palette(palette)
    svc.background(svc.player.resume())
    return _view(svc)


@router.post("/cancel", status_code=202)
async def cancel(svc: Svc) -> dict[str, Any]:
    """Take the chart off the frame without changing anything."""
    svc.background(svc.player.resume())
    return {"accepted": True}


@router.delete("", response_model=CalibrationView)
async def reset(svc: Svc) -> CalibrationView:
    """Forget the measured palette and go back to the default one."""
    svc.set_palette(None)
    svc.background(svc.player.resume())
    return _view(svc)
