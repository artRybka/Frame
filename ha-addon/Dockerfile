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

# Two ways to get the server code:
#  * scripts/bundle-addon.sh copies ./server next to this Dockerfile (local
#    add-on on the HA box, CI image builds) -> install that copy;
#  * otherwise (add-on installed from the GitHub repository) -> pip install
#    straight from git at FRAME_REF.
COPY . /addon
RUN if [ -d /addon/server ]; then \
        pip install /addon/server; \
    else \
        pip install "frame-server @ git+https://github.com/artRybka/Frame@${FRAME_REF}#subdirectory=server"; \
    fi \
    && rm -rf /addon

WORKDIR /data
CMD ["frame", "serve"]
