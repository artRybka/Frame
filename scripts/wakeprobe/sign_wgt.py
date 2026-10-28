"""Package and sign a Tizen web app without Tizen Studio (W3C widget signing).

    sign_wgt.py SRC_DIR OUT.wgt [CERT_DIR]      default CERT_DIR: ~/SamsungCertificate/frame

CERT_DIR holds the Samsung profile from Tizen Studio's Certificate Manager
(author.p12, distributor.p12) and a `.password` file (chmod 600). The output is
accepted by the EM32DX launcher like a `tizen package` build (tested 2026-10-28).
Never commit the certificate files or the password.
"""

import base64
import hashlib
import sys
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

DS = "http://www.w3.org/2000/09/xmldsig#"


def load_identity(cert_dir: Path, role: str):
    """(private key, [leaf, intermediates]) from <role>.p12."""
    password = (cert_dir / ".password").read_bytes().strip()
    key, cert, extra = pkcs12.load_key_and_certificates((cert_dir / f"{role}.p12").read_bytes(), password)
    return key, [cert] + [c for c in (extra or []) if c.subject != c.issuer]


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def signature(files: dict[str, bytes], sig_id: str, role: str, key, certs) -> bytes:
    """Signature XML over files (path -> bytes). SignedInfo and the #prop object
    are written already in canonical form, so their digests need no C14N library."""
    obj_inner = (
        '<SignatureProperties xmlns:dsp="http://www.w3.org/2009/xmldsig-properties">'
        f'<SignatureProperty Id="profile" Target="#{sig_id}"><dsp:Profile URI="http://www.w3.org/ns/widgets-digsig#profile"></dsp:Profile></SignatureProperty>'
        f'<SignatureProperty Id="role" Target="#{sig_id}"><dsp:Role URI="http://www.w3.org/ns/widgets-digsig#role-{role}"></dsp:Role></SignatureProperty>'
        f'<SignatureProperty Id="identifier" Target="#{sig_id}"><dsp:Identifier></dsp:Identifier></SignatureProperty>'
        "</SignatureProperties>"
    )
    obj_c14n = f'<Object xmlns="{DS}" Id="prop">{obj_inner}</Object>'
    refs = ""
    for path, data in files.items():
        refs += (
            f'<Reference URI="{path}">\n<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></DigestMethod>\n'
            f"<DigestValue>{b64(hashlib.sha256(data).digest())}</DigestValue>\n</Reference>\n"
        )
    refs += (
        '<Reference URI="#prop">\n<Transforms>\n<Transform Algorithm="http://www.w3.org/2006/12/xml-c14n11"></Transform>\n</Transforms>\n'
        '<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"></DigestMethod>\n'
        f"<DigestValue>{b64(hashlib.sha256(obj_c14n.encode()).digest())}</DigestValue>\n</Reference>\n"
    )
    si_inner = (
        '\n<CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"></CanonicalizationMethod>\n'
        '<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"></SignatureMethod>\n' + refs
    )
    value = key.sign(f'<SignedInfo xmlns="{DS}">{si_inner}</SignedInfo>'.encode(), padding.PKCS1v15(), hashes.SHA256())
    x509s = "".join(f"<X509Certificate>\n{b64(c.public_bytes(serialization.Encoding.DER))}\n</X509Certificate>\n" for c in certs)
    return (
        f'<Signature xmlns="{DS}" Id="{sig_id}">\n<SignedInfo>{si_inner}</SignedInfo>\n'
        f"<SignatureValue>\n{b64(value)}\n</SignatureValue>\n"
        f"<KeyInfo>\n<X509Data>\n{x509s}</X509Data>\n</KeyInfo>\n"
        f'<Object Id="prop">{obj_inner}</Object>\n</Signature>'
    ).encode()


def build(src: Path, out: Path, cert_dir: Path) -> int:
    files = {
        p.relative_to(src).as_posix(): p.read_bytes()
        for p in sorted(src.rglob("*"))
        if p.is_file() and not p.name.startswith(".") and p.suffix != ".wgt" and p.name not in ("author-signature.xml", "signature1.xml")
    }
    author = signature(files, "AuthorSignature", "author", *load_identity(cert_dir, "author"))
    dist = signature({"author-signature.xml": author, **files}, "DistributorSignature", "distributor",
                     *load_identity(cert_dir, "distributor"))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in {**files, "author-signature.xml": author, "signature1.xml": dist}.items():
            z.writestr(path, data)
    return out.stat().st_size


if __name__ == "__main__":
    certs = Path(sys.argv[3]) if len(sys.argv) > 3 else Path.home() / "SamsungCertificate" / "frame"
    size = build(Path(sys.argv[1]), Path(sys.argv[2]), certs)
    print(f"{sys.argv[2]} ({size} bytes)")
