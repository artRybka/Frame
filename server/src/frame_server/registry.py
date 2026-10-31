"""What the image registry has under a tag, without downloading the image.

"Sprawdź aktualizacje" used to wait for `frame updater` to pull the image:
a few seconds when nothing changed, minutes on the NAS when a new release was
out (each one brought a ~200 MB layer). The server asks the registry itself
instead: the tag's manifest and the image config (a few kB, with the
version labels publish.yml sets) are enough to tell, in about a second.
"""

from __future__ import annotations

import platform
import re

import httpx

from .updates import ImageInfo

DEFAULT_IMAGE = "ghcr.io/artrybka/frame:latest"
TIMEOUT = httpx.Timeout(8.0, connect=5.0)

_INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)
_MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
)
ACCEPT = ", ".join(_INDEX_TYPES + _MANIFEST_TYPES)


class RegistryError(RuntimeError):
    pass


def parse_ref(ref: str) -> tuple[str, str, str]:
    """``[host/]repo[:tag]`` → (registry host, repository, tag)."""
    if "@" in ref:
        raise RegistryError(f"obraz {ref} jest przypięty do skrótu")
    name, sep, tag = ref.rpartition(":")
    if not sep or "/" in tag:
        name, tag = ref, "latest"
    first, _, rest = name.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        host, repo = first, rest
    else:  # Docker Hub
        host, repo = "registry-1.docker.io", name
        if "/" not in repo:
            repo = f"library/{repo}"
    return host, repo, tag


def docker_arch(machine: str | None = None) -> str:
    machine = (machine or platform.machine()).lower()
    return {"x86_64": "amd64", "aarch64": "arm64", "armv8": "arm64"}.get(machine, machine)


def _challenge(header: str) -> dict[str, str]:
    """``Bearer realm="…",service="…",scope="…"`` → its fields."""
    return dict(re.findall(r'(\w+)="([^"]*)"', header))


class Registry:
    """Anonymous reads of the Docker Registry HTTP API v2 (ghcr.io, Docker
    Hub): the image is public, so a pull token for the asking is enough."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.token: str | None = None

    def _get(self, url: str, accept: str | None = None) -> httpx.Response:
        headers = {"Accept": accept} if accept else {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.client.get(url, headers=headers)
        if response.status_code == 401 and self.token is None:
            fields = _challenge(response.headers.get("www-authenticate", ""))
            if "realm" not in fields:
                raise RegistryError(f"{url}: 401 bez wskazania, skąd wziąć token")
            params = {k: v for k, v in fields.items() if k in ("service", "scope")}
            auth = self.client.get(fields["realm"], params=params)
            if auth.status_code >= 400:
                raise RegistryError(f"token rejestru: {auth.status_code}")
            body = auth.json()
            self.token = body.get("token") or body.get("access_token")
            if not self.token:
                raise RegistryError("rejestr nie dał tokenu")
            return self._get(url, accept)
        if response.status_code >= 400:
            raise RegistryError(f"{url}: {response.status_code}")
        return response

    def latest(self, ref: str, arch: str | None = None) -> ImageInfo:
        """The image ``ref`` points at for this machine's architecture: its
        id (the config digest, which is what Docker calls the image id) and
        its version labels."""
        host, repo, tag = parse_ref(ref)
        base = f"https://{host}/v2/{repo}"
        manifest = self._get(f"{base}/manifests/{tag}", ACCEPT).json()
        if manifest.get("mediaType") in _INDEX_TYPES or "manifests" in manifest:
            arch = arch or docker_arch()
            digest = next(
                (
                    m["digest"]
                    for m in manifest.get("manifests") or []
                    if (m.get("platform") or {}).get("os") == "linux"
                    and (m.get("platform") or {}).get("architecture") == arch
                ),
                None,
            )
            if digest is None:
                raise RegistryError(f"{ref} nie ma obrazu dla linux/{arch}")
            manifest = self._get(f"{base}/manifests/{digest}", ACCEPT).json()
        config_digest = (manifest.get("config") or {}).get("digest")
        if not config_digest:
            raise RegistryError(f"{ref}: manifest bez konfiguracji obrazu")
        config = self._get(f"{base}/blobs/{config_digest}").json()
        labels = (config.get("config") or {}).get("Labels") or {}
        return ImageInfo(
            id=config_digest,
            version=labels.get("org.opencontainers.image.version") or None,
            revision=labels.get("org.opencontainers.image.revision") or None,
            created=config.get("created"),
        )


def latest_image(ref: str = DEFAULT_IMAGE, client: httpx.Client | None = None) -> ImageInfo:
    if client is not None:
        return Registry(client).latest(ref)
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as own:
        return Registry(own).latest(ref)
