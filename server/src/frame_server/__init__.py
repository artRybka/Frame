"""Frame: home art & photo frame server for the Samsung EM32DX e-paper panel."""

import os
from pathlib import Path

__version__ = "0.1.0"

# Written by the image build (ha-addon/Dockerfile) from the add-on version.
RELEASE_FILE = Path("/etc/frame-release")


def build_version() -> str:
    """The release this server is: the add-on version baked into the image,
    or the package version when run from source."""
    if version := os.environ.get("FRAME_RELEASE"):
        return version
    try:
        return RELEASE_FILE.read_text().strip() or __version__
    except OSError:
        return __version__
