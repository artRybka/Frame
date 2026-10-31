#!/usr/bin/env python3
"""Release version and "What to Test" notes for TestFlight uploads.

Used by .github/workflows/testflight.yml. Standard library only (plus the
`openssl` binary for the ES256 signature), so it runs on any runner.

    testflight-notes.py version
        Print the release version from ha-addon/config.yaml (e.g. 1.47.0).

    testflight-notes.py notes [VERSION]
        Print that version's CHANGELOG section as plain text.

    testflight-notes.py upload --bundle-id ID --version V --build N
        Wait until App Store Connect has processed build N of version V and
        set its "What to Test" text (every beta build localization, plus the
        app's primary language) to the CHANGELOG section of V.
        Needs ASC_KEY_ID, ASC_ISSUER_ID and ASC_KEY_PATH in the environment.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "ha-addon" / "config.yaml"
CHANGELOG = ROOT / "ha-addon" / "CHANGELOG.md"
API = "https://api.appstoreconnect.apple.com"
WHATS_NEW_LIMIT = 4000  # App Store Connect rejects longer text


def release_version() -> str:
    match = re.search(r'^version:\s*"?([0-9][0-9.]*)"?\s*$', CONFIG.read_text(), re.M)
    if not match:
        raise SystemExit(f"no version in {CONFIG}")
    version = match.group(1)
    # CFBundleShortVersionString: one to three dot-separated integers.
    if not re.fullmatch(r"\d+(\.\d+){0,2}", version):
        raise SystemExit(f"{version!r} is not a valid CFBundleShortVersionString")
    # Builds before 0.46.1 went out as 1.0; TestFlight hides anything lower
    # than the highest version it has seen instead of offering it as an update.
    if int(version.split(".")[0]) < 1:
        raise SystemExit(f"{version} is lower than 1.0, TestFlight would not offer it")
    return version


def changelog_section(version: str, text: str | None = None) -> str:
    """The section under `## <version>`, unwrapped into one line per bullet."""
    text = CHANGELOG.read_text() if text is None else text
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == version
            continue
        if inside:
            lines.append(line)

    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if items and items[-1]:
                items.append("")
            continue
        if stripped.startswith(("- ", "* ")):
            items.append("• " + stripped[2:])
        elif items and items[-1]:
            items[-1] += " " + stripped  # continuation of a wrapped bullet
        else:
            items.append(stripped)
    # One bullet per line; keep blank lines only between paragraphs.
    out: list[str] = []
    for item in items:
        if item == "" and out and out[-1].startswith("• "):
            continue
        out.append(item)
    notes = "\n".join(out).strip()
    if len(notes) > WHATS_NEW_LIMIT:
        notes = notes[: WHATS_NEW_LIMIT - 1].rstrip() + "…"
    return notes


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _der_to_raw(der: bytes) -> bytes:
    """ECDSA signature: DER SEQUENCE{INTEGER r, INTEGER s} → r||s (64 bytes)."""
    if der[0] != 0x30:
        raise ValueError("not a DER sequence")
    pos = 2 if der[1] < 0x80 else 2 + (der[1] & 0x7F)
    parts = []
    for _ in range(2):
        if der[pos] != 0x02:
            raise ValueError("not a DER integer")
        length = der[pos + 1]
        value = der[pos + 2 : pos + 2 + length].lstrip(b"\0")
        parts.append(value.rjust(32, b"\0"))
        pos += 2 + length
    return b"".join(parts)


class Connect:
    def __init__(self, key_id: str, issuer_id: str, key_path: str) -> None:
        self.key_id, self.issuer_id, self.key_path = key_id, issuer_id, key_path
        self._token, self._expires = "", 0.0

    def token(self) -> str:
        now = time.time()
        if now < self._expires - 60:
            return self._token
        header = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}
        payload = {
            "iss": self.issuer_id,
            "iat": int(now),
            "exp": int(now) + 15 * 60,
            "aud": "appstoreconnect-v1",
        }
        signing_input = (
            _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(payload).encode())
        )
        der = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", self.key_path],
            input=signing_input.encode(),
            capture_output=True,
            check=True,
        ).stdout
        self._token = signing_input + "." + _b64url(_der_to_raw(der))
        self._expires = now + 15 * 60
        return self._token

    def call(self, method: str, path: str, body: dict | None = None) -> dict:
        request = urllib.request.Request(
            API + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")
            raise RuntimeError(f"{method} {path}: HTTP {error.code} {detail}") from None
        return json.loads(raw) if raw else {}


def wait_for_build(asc: Connect, app_id: str, version: str, build: str, timeout: float) -> dict:
    query = urllib.parse.urlencode(
        {
            "filter[app]": app_id,
            "filter[version]": build,
            "filter[preReleaseVersion.version]": version,
            "limit": "1",
        }
    )
    deadline = time.time() + timeout
    state = "not visible yet"
    while time.time() < deadline:
        try:
            builds = asc.call("GET", f"/v1/builds?{query}")["data"]
        except RuntimeError as error:  # transient API trouble: keep waiting
            print(f"::warning::{error}")
            builds = []
        if builds:
            state = builds[0]["attributes"].get("processingState", "")
            if state == "VALID":
                return builds[0]
            if state in ("FAILED", "INVALID"):
                raise SystemExit(f"build {version} ({build}) is {state}")
        print(f"build {version} ({build}): {state}, waiting")
        time.sleep(30)
    raise SystemExit(f"build {version} ({build}) still {state} after {timeout / 60:.0f} min")


def upload(bundle_id: str, version: str, build: str, timeout: float) -> None:
    notes = changelog_section(version)
    if not notes:
        print(f"::warning::CHANGELOG has no section for {version}; What to Test left empty")
        return
    asc = Connect(os.environ["ASC_KEY_ID"], os.environ["ASC_ISSUER_ID"], os.environ["ASC_KEY_PATH"])
    query = urllib.parse.urlencode({"filter[bundleId]": bundle_id, "limit": "1"})
    apps = asc.call("GET", f"/v1/apps?{query}")["data"]
    if not apps:
        raise SystemExit(f"no app with bundle id {bundle_id}")
    app = apps[0]
    found = wait_for_build(asc, app["id"], version, build, timeout)

    existing = asc.call("GET", f"/v1/builds/{found['id']}/betaBuildLocalizations")["data"]
    for loc in existing:
        asc.call(
            "PATCH",
            f"/v1/betaBuildLocalizations/{loc['id']}",
            {
                "data": {
                    "type": "betaBuildLocalizations",
                    "id": loc["id"],
                    "attributes": {"whatsNew": notes},
                }
            },
        )
        print(f"What to Test set ({loc['attributes']['locale']})")
    locales = {loc["attributes"]["locale"] for loc in existing}
    primary = app["attributes"].get("primaryLocale") or "pl"
    if primary not in locales:
        asc.call(
            "POST",
            "/v1/betaBuildLocalizations",
            {
                "data": {
                    "type": "betaBuildLocalizations",
                    "attributes": {"locale": primary, "whatsNew": notes},
                    "relationships": {"build": {"data": {"type": "builds", "id": found["id"]}}},
                }
            },
        )
        print(f"What to Test set ({primary})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("version")
    notes = sub.add_parser("notes")
    notes.add_argument("version", nargs="?")
    up = sub.add_parser("upload")
    up.add_argument("--bundle-id", required=True)
    up.add_argument("--version", required=True)
    up.add_argument("--build", required=True)
    up.add_argument("--timeout-min", type=float, default=45)
    args = parser.parse_args()

    if args.command == "version":
        print(release_version())
    elif args.command == "notes":
        print(changelog_section(args.version or release_version()))
    else:
        upload(args.bundle_id, args.version, args.build, args.timeout_min * 60)


if __name__ == "__main__":
    sys.exit(main())
