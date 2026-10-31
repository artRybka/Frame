import sys
from pathlib import Path

import pytest
from PIL import Image

# Lets tests import helper modules (fake_panel) that live next to them.
sys.path.insert(0, str(Path(__file__).parent))


def jpeg_bytes(color: tuple[int, int, int], size: tuple[int, int] = (320, 240)) -> bytes:
    import io

    img = Image.new("RGB", size, color)
    # A second colour block so palettes have some structure.
    img.paste((20, 20, 20), (0, 0, size[0] // 4, size[1] // 4))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def service(tmp_path: Path):
    from frame_server.config import Settings
    from frame_server.service import FrameService

    settings = Settings(
        data_dir=tmp_path, seed_library=False, scheduler=False, public_host="127.0.0.1"
    )
    svc = FrameService(settings)
    svc.ensure_initial_content()
    return svc


# Services in the tests start daemon threads (AI workers, the daily job,
# artist-works and study-details lookups) that can still be inside C code when
# the interpreter shuts down, which now and then crashed CI with exit 139 after
# every test had passed. Once pytest has reported, end the process with its
# own exit status instead of tearing those threads down.
_exit_status: int | None = None


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    global _exit_status
    _exit_status = int(exitstatus)


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: pytest.Config) -> None:
    if _exit_status is None:
        return
    import os

    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(_exit_status)
