ARG BUILD_FROM=python:3.13-slim-bookworm
FROM ${BUILD_FROM}

ARG FRAME_REF=main
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NUMBA_CACHE_DIR=/tmp/numba-cache \
    FRAME_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends git fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# The dependencies first, in a layer of their own: it stays the same from one
# release to the next (until pyproject.toml changes), so a server update on
# the NAS downloads a few MB of server code instead of ~200 MB of numpy,
# numba, OpenCV, ... every time. Only the bundled build has the pyproject
# (the wildcards let the COPY find nothing else); from git, the step below
# installs everything as before.
COPY build.yaml serve[r]/pyproject.tom[l] /deps/
RUN if [ -f /deps/pyproject.toml ]; then \
        python -c "import tomllib; print('\n'.join(tomllib.load(open('/deps/pyproject.toml', 'rb'))['project']['dependencies']))" > /deps/requirements.txt \
        && pip install -r /deps/requirements.txt; \
    fi \
    && rm -rf /deps

# Two ways to get the server code:
#  * scripts/bundle-addon.sh copies ./server next to this Dockerfile (local
#    add-on on the HA box, CI image builds) -> install that copy;
#  * otherwise (add-on installed from the GitHub repository) -> pip install
#    straight from git at FRAME_REF.
# The add-on version goes to /etc/frame-release: the version the server reports.
COPY . /addon
RUN if [ -d /addon/server ]; then \
        pip install /addon/server; \
    else \
        pip install "frame-server @ git+https://github.com/artRybka/Frame@${FRAME_REF}#subdirectory=server"; \
    fi \
    && sed -n 's/^version: *"\{0,1\}\([^"]*\)"\{0,1\}$/\1/p' /addon/config.yaml > /etc/frame-release \
    && rm -rf /addon \
    && python -c "from frame_server.imaging.interest import detect_faces, _face_detector; assert _face_detector()"

WORKDIR /data
CMD ["frame", "serve"]
