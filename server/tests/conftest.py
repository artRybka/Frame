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
