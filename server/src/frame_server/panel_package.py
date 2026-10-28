"""Build and sign the frame's app package (.wgt) on the server.

The launcher installs only a package signed with the Samsung certificates
made for this panel (author and distributor, Tizen Studio's Certificate
Manager, the panel's DUID). They and their password are uploaded once to the
data directory and never leave it: not in the repository, not in a log.

Signing is the W3C widget digital signature (author-signature.xml, then
signature1.xml over it), written already in canonical form so no XML
library is needed; packages built this way were installed and run by the
EM32DX launcher (E16, scripts/wakeprobe/sign_wgt.py, 2026-10-28).
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from pydantic import BaseModel

log = logging.getLogger(__name__)

DS = "http://www.w3.org/2000/09/xmldsig#"
ROLES = ("author", "distributor")
PASSWORD = ".password"
SIGNATURES = ("author-signature.xml", "signature1.xml")


class CertificateInfo(BaseModel):
    role: str
    subject: str
    expires_at: str  # ISO


class Identity:
    def __init__(self, key: rsa.RSAPrivateKey, certs: list[x509.Certificate]) -> None:
        self.key = key
        self.certs = certs


def load_identity(data: bytes, password: bytes) -> Identity:
    """Key and chain (leaf first, no self-signed root) from a .p12; raises
    ValueError for a wrong password or a file that is not one."""
    key, cert, extra = pkcs12.load_key_and_certificates(data, password)
    if not isinstance(key, rsa.RSAPrivateKey) or cert is None:
        raise ValueError("the .p12 has no RSA key and certificate")
    chain = [cert] + [c for c in (extra or []) if c.subject != c.issuer]
    return Identity(key, chain)


class Certificates:
    """author.p12, distributor.p12 and the password in ``dir`` (mode 600)."""

    def __init__(self, dir: Path) -> None:
        self.dir = dir
        self._info: tuple[tuple[float, ...], list[CertificateInfo]] | None = None

    def present(self) -> bool:
        files = [*(f"{role}.p12" for role in ROLES), PASSWORD]
        return all((self.dir / name).is_file() for name in files)

    def save(self, author: bytes, distributor: bytes, password: bytes) -> list[CertificateInfo]:
        """Check that the password opens both, then keep them."""
        password = password.strip()
        found = {"author": author, "distributor": distributor}
        infos = [_info(role, load_identity(data, password)) for role, data in found.items()]
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        for name, data in ((f"{r}.p12", d) for r, d in found.items()):
            _write_private(self.dir / name, data)
        _write_private(self.dir / PASSWORD, password)
        log.info("panel app certificates stored (valid until %s)", _earliest(infos))
        return infos

    def identity(self, role: str) -> Identity:
        password = (self.dir / PASSWORD).read_bytes().strip()
        return load_identity((self.dir / f"{role}.p12").read_bytes(), password)

    def info(self) -> list[CertificateInfo]:
        """What is stored; empty when nothing (or something unreadable) is.
        Read again only when the files change (the status asks often)."""
        if not self.present():
            return []
        files = [*(self.dir / f"{role}.p12" for role in ROLES), self.dir / PASSWORD]
        try:
            stamp = tuple(path.stat().st_mtime for path in files)
            if self._info is None or self._info[0] != stamp:
                self._info = (stamp, [_info(role, self.identity(role)) for role in ROLES])
        except (OSError, ValueError) as err:
            log.warning("panel app certificates unreadable: %s", err)
            return []
        return self._info[1]

    def expires_at(self) -> datetime | None:
        infos = self.info()
        return datetime.fromisoformat(_earliest(infos)) if infos else None


def _write_private(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".part")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    tmp.replace(path)


def _info(role: str, identity: Identity) -> CertificateInfo:
    leaf = identity.certs[0]
    return CertificateInfo(
        role=role,
        subject=leaf.subject.rfc4514_string(),
        expires_at=leaf.not_valid_after_utc.astimezone(UTC).isoformat(timespec="seconds"),
    )


def _earliest(infos: list[CertificateInfo]) -> str:
    return min(info.expires_at for info in infos)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _signature(files: dict[str, bytes], sig_id: str, role: str, who: Identity) -> bytes:
    """The signature XML over ``files`` (path -> bytes). SignedInfo and the
    #prop object are written in their canonical form, so their digests need
    no canonicalisation."""
    props = (
        '<SignatureProperties xmlns:dsp="http://www.w3.org/2009/xmldsig-properties">'
        f'<SignatureProperty Id="profile" Target="#{sig_id}">'
        '<dsp:Profile URI="http://www.w3.org/ns/widgets-digsig#profile"></dsp:Profile>'
        "</SignatureProperty>"
        f'<SignatureProperty Id="role" Target="#{sig_id}">'
        f'<dsp:Role URI="http://www.w3.org/ns/widgets-digsig#role-{role}"></dsp:Role>'
        "</SignatureProperty>"
        f'<SignatureProperty Id="identifier" Target="#{sig_id}">'
        "<dsp:Identifier></dsp:Identifier></SignatureProperty>"
        "</SignatureProperties>"
    )
    prop_c14n = f'<Object xmlns="{DS}" Id="prop">{props}</Object>'
    sha256 = '<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></DigestMethod>\n'
    refs = "".join(
        f'<Reference URI="{path}">\n{sha256}'
        f"<DigestValue>{_b64(hashlib.sha256(data).digest())}</DigestValue>\n</Reference>\n"
        for path, data in files.items()
    )
    refs += (
        '<Reference URI="#prop">\n<Transforms>\n'
        '<Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></Transform>\n'
        f"</Transforms>\n{sha256}"
        f"<DigestValue>{_b64(hashlib.sha256(prop_c14n.encode()).digest())}</DigestValue>\n"
        "</Reference>\n"
    )
    signed = (
        '\n<CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#">'
        "</CanonicalizationMethod>\n"
        '<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256">'
        "</SignatureMethod>\n" + refs
    )
    value = who.key.sign(
        f'<SignedInfo xmlns="{DS}">{signed}</SignedInfo>'.encode(),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    certs = "".join(
        f"<X509Certificate>\n{_b64(c.public_bytes(serialization.Encoding.DER))}\n"
        "</X509Certificate>\n"
        for c in who.certs
    )
    return (
        f'<Signature xmlns="{DS}" Id="{sig_id}">\n<SignedInfo>{signed}</SignedInfo>\n'
        f"<SignatureValue>\n{_b64(value)}\n</SignatureValue>\n"
        f"<KeyInfo>\n<X509Data>\n{certs}</X509Data>\n</KeyInfo>\n"
        f'<Object Id="prop">{props}</Object>\n</Signature>'
    ).encode()


def sign_package(files: dict[str, bytes], certificates: Certificates) -> bytes:
    """The .wgt (zip) of ``files`` (path -> bytes), signed by the author and
    then by the distributor."""
    files = {path: files[path] for path in sorted(files) if path not in SIGNATURES}
    author = _signature(files, "AuthorSignature", "author", certificates.identity("author"))
    distributor = _signature(
        {SIGNATURES[0]: author, **files},
        "DistributorSignature",
        "distributor",
        certificates.identity("distributor"),
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in {**files, SIGNATURES[0]: author, SIGNATURES[1]: distributor}.items():
            z.writestr(path, data)
    return out.getvalue()
