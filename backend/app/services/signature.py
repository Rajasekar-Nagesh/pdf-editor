"""Signatures.

* Simple signatures: a drawn / typed / uploaded image placed on a page.
* Digital signatures with pyHanko: PKCS#12 (.pfx/.p12) certificate, or a USB DSC token through a
  two-step "prepare / complete" flow where the token signs on the user's own computer.
* Validation of existing digital signatures.

Certificate files and passwords are only ever held in memory for the duration of a request.
"""
import asyncio
import base64
import binascii
import io
from datetime import datetime, timezone
from pathlib import Path

import pikepdf
import pymupdf as fitz
from asn1crypto import cms, pem, x509
from pyhanko import stamp
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers, timestamps
from pyhanko.sign.signers.pdf_byterange import PreparedByteRangeDigest
from pyhanko.sign.signers.pdf_signer import PdfTBSDocument
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore

from .common import ToolContext, ToolError, ToolOutput, open_pdf, require_page, save_pdf, visible_to_unrotated

MAX_SIGNATURE_IMAGE = 3 * 1024 * 1024
STAMP_TEXT = "Digitally signed by %(signer)s\nDate: %(ts)s\nReason: %(reason)s\nLocation: %(location)s"


# ------------------------------------------------------------------ simple signature


def decode_image_data(data_url: str) -> bytes:
    """Decode a data: URL / base64 PNG produced by the signature pad."""
    if "," in data_url and data_url.startswith("data:"):
        data_url = data_url.split(",", 1)[1]
    try:
        raw = base64.b64decode(data_url, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ToolError("The signature image is not valid.") from exc
    if len(raw) > MAX_SIGNATURE_IMAGE:
        raise ToolError("The signature image is too large (max 3 MB).")
    from ..validation import is_image_bytes

    if not is_image_bytes(raw):
        raise ToolError("The signature must be an image.")
    return raw


def place_signature(
    ctx: ToolContext,
    placements: list[dict],
    image_data: str = "",
    image_file_id: str | None = None,
) -> ToolOutput:
    """Place a signature image at one or more {page, rect} positions (visible coordinates)."""
    if ctx.assets.get("image_file_id"):
        img = ctx.assets["image_file_id"].read_bytes()
    elif image_data:
        img = decode_image_data(image_data)
    else:
        raise ToolError("Draw, type or upload a signature first.")
    if not placements:
        raise ToolError("Click on the page to place your signature.")
    doc = open_pdf(ctx.inputs[0])
    for pl in placements:
        page = require_page(doc, int(pl.get("page", 0)))
        page.insert_image(visible_to_unrotated(page, pl["rect"]), stream=img, keep_proportion=True)
    name = f"{ctx.stem}-signed.pdf"
    return ToolOutput(files=[(save_pdf(doc, ctx.out(name)), name)])


# ------------------------------------------------------------------ digital signature helpers


def _pdf_box(pdf_path: Path, page: int, rect: list[float]) -> tuple[int, int, int, int]:
    """Convert a visible top-left rect to PDF user-space (bottom-left origin) for pyHanko."""
    with pikepdf.open(pdf_path) as pdf:
        if not 0 <= page < len(pdf.pages):
            raise ToolError("That page does not exist.")
        llx, lly, urx, ury = [float(v) for v in pikepdf.Page(pdf.pages[page]).cropbox]
    x0, y0, x1, y1 = [float(v) for v in rect]
    return (int(llx + x0), int(ury - y1), int(llx + x1), int(ury - y0))


def _field_name(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    existing = {w.field_name for p in doc for w in p.widgets()}
    doc.close()
    n = 1
    while f"Signature{n}" in existing:
        n += 1
    return f"Signature{n}"


def _check_not_encrypted(pdf_path: Path) -> None:
    doc = fitz.open(pdf_path)
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise ToolError("Remove the password from this PDF before signing it.")
    finally:
        doc.close()


def _signer_setup(pdf_path: Path, page: int, rect: list[float] | None, reason: str, location: str, contact: str):
    field = _field_name(pdf_path)
    meta = signers.PdfSignatureMetadata(
        field_name=field,
        reason=reason or None,
        location=location or None,
        contact_info=contact or None,
        md_algorithm="sha256",
        subfilter=fields.SigSeedSubFilter.ADOBE_PKCS7_DETACHED,
    )
    spec = fields.SigFieldSpec(field, on_page=int(page), box=_pdf_box(pdf_path, int(page), rect) if rect else None)
    style = stamp.TextStampStyle(stamp_text=STAMP_TEXT, border_width=1)
    params = {"reason": reason or "-", "location": location or "-"}
    return meta, spec, style, params


def sign_pkcs12(
    pdf_path: Path,
    out_path: Path,
    pfx: bytes,
    password: str,
    page: int = 0,
    rect: list[float] | None = None,
    reason: str = "",
    location: str = "",
    contact: str = "",
    tsa_url: str = "",
) -> dict:
    _check_not_encrypted(pdf_path)
    try:
        signer = signers.SimpleSigner.load_pkcs12_data(pfx, other_certs=[], passphrase=password.encode() if password else None)
    except Exception as exc:
        raise ToolError("Could not open the certificate. Check the file and its password.") from exc
    if signer is None or signer.signing_cert is None:
        raise ToolError("Could not open the certificate. Check the file and its password.")
    meta, spec, style, params = _signer_setup(pdf_path, page, rect, reason, location, contact)
    timestamper = timestamps.HTTPTimeStamper(tsa_url, timeout=15) if tsa_url else None
    pdf_signer = signers.PdfSigner(meta, signer=signer, stamp_style=style, new_field_spec=spec, timestamper=timestamper)
    with open(pdf_path, "rb") as inf:
        w = IncrementalPdfFileWriter(inf, strict=False)
        with open(out_path, "wb") as outf:
            try:
                pdf_signer.sign_pdf(w, output=outf, appearance_text_params=params)
            except Exception as exc:
                raise ToolError(f"Signing failed: {exc.__class__.__name__}") from exc
    cert = signer.signing_cert
    return {"signer": cert.subject.human_friendly, "field": meta.field_name, "serial": str(cert.serial_number)}


# ------------------------------------------------------------------ USB token (two-step) signing


def load_certificates(data: str) -> list[x509.Certificate]:
    """Accept PEM (one or more certs) or base64 DER. The first certificate is the signer."""
    raw = data.encode() if isinstance(data, str) else data
    certs = []
    try:
        if pem.detect(raw):
            for _type, _hdr, der in pem.unarmor(raw, multiple=True):
                certs.append(x509.Certificate.load(der))
        else:
            certs.append(x509.Certificate.load(base64.b64decode(raw)))
        for c in certs:
            _ = c.subject  # force parse
    except Exception as exc:
        raise ToolError("The certificate from the token could not be read.") from exc
    if not certs:
        raise ToolError("No certificate was provided by the token.")
    return certs


def dsc_prepare(
    pdf_path: Path,
    out_path: Path,
    cert_data: str,
    page: int = 0,
    rect: list[float] | None = None,
    reason: str = "",
    location: str = "",
    contact: str = "",
) -> dict:
    """Step 1: reserve the signature in the PDF and return the bytes the token must sign."""
    _check_not_encrypted(pdf_path)
    certs = load_certificates(cert_data)
    meta, spec, style, params = _signer_setup(pdf_path, page, rect, reason, location, contact)
    ext = signers.ExternalSigner(
        signing_cert=certs[0], cert_registry=SimpleCertificateStore.from_certs(certs), signature_value=bytes(512)
    )
    pdf_signer = signers.PdfSigner(meta, signer=ext, stamp_style=style, new_field_spec=spec)

    async def _run():
        with open(pdf_path, "rb") as inf:
            w = IncrementalPdfFileWriter(io.BytesIO(inf.read()), strict=False)
        prep, _tbs, output = await pdf_signer.async_digest_doc_for_signing(
            w, bytes_reserved=32768, appearance_text_params=params
        )
        attrs = await ext.signed_attrs(prep.document_digest, "sha256", use_pades=False)
        return prep, output, attrs

    prep, output, attrs = asyncio.run(_run())
    output.seek(0)
    out_path.write_bytes(output.read())
    attrs_der = attrs.dump()
    return {
        "to_sign": base64.b64encode(attrs_der).decode(),  # the token signs SHA256(to_sign) with RSA/ECDSA
        "digest_algorithm": "sha256",
        "state": {
            "document_digest": base64.b64encode(prep.document_digest).decode(),
            "reserved_region_start": prep.reserved_region_start,
            "reserved_region_end": prep.reserved_region_end,
            "signed_attrs": base64.b64encode(attrs_der).decode(),
            "certs": [base64.b64encode(c.dump()).decode() for c in certs],
        },
    }


def dsc_complete(prepared_path: Path, out_path: Path, state: dict, signature_b64: str) -> dict:
    """Step 2: embed the signature value produced by the token into the prepared PDF."""
    try:
        signature = base64.b64decode(signature_b64)
    except (binascii.Error, ValueError) as exc:
        raise ToolError("The signature returned by the token is not valid base64.") from exc
    certs = [x509.Certificate.load(base64.b64decode(c)) for c in state["certs"]]
    attrs = cms.CMSAttributes.load(base64.b64decode(state["signed_attrs"]))
    prep = PreparedByteRangeDigest(
        document_digest=base64.b64decode(state["document_digest"]),
        reserved_region_start=int(state["reserved_region_start"]),
        reserved_region_end=int(state["reserved_region_end"]),
    )
    ext = signers.ExternalSigner(
        signing_cert=certs[0], cert_registry=SimpleCertificateStore.from_certs(certs), signature_value=signature
    )

    async def _run():
        sig_cms = await ext.async_sign_prescribed_attributes("sha256", signed_attrs=attrs)
        buf = io.BytesIO(prepared_path.read_bytes())
        await PdfTBSDocument.async_finish_signing(buf, prep, sig_cms)
        return buf.getvalue()

    try:
        out_path.write_bytes(asyncio.run(_run()))
    except Exception as exc:
        raise ToolError(f"Could not embed the token signature: {exc.__class__.__name__}") from exc
    return {"signer": certs[0].subject.human_friendly}


# ------------------------------------------------------------------ validation


def validate_signatures(ctx: ToolContext, check_revocation: bool = False) -> ToolOutput:
    results = []
    with open(ctx.inputs[0], "rb") as f:
        try:
            reader = PdfFileReader(f, strict=False)
        except Exception as exc:
            raise ToolError("This PDF could not be read for signature validation.") from exc
        sigs = reader.embedded_signatures
        for sig in sigs:
            entry = {"field": sig.field_name}
            try:
                vc = ValidationContext(allow_fetching=bool(check_revocation))
                status = validate_pdf_signature(sig, vc)
                cert = status.signing_cert
                entry.update(
                    {
                        "signer": cert.subject.human_friendly if cert else "Unknown",
                        "issuer": cert.issuer.human_friendly if cert else "",
                        "signing_time": status.signer_reported_dt.isoformat() if status.signer_reported_dt else None,
                        "intact": bool(status.intact),
                        "valid": bool(status.valid),
                        "trusted": bool(status.trusted),
                        "coverage": status.coverage.name if status.coverage else None,
                        "modification_level": status.modification_level.name if status.modification_level else None,
                        "summary": status.summary(),
                        "timestamped": status.timestamp_validity is not None,
                    }
                )
            except Exception as exc:
                entry.update({"intact": False, "valid": False, "trusted": False, "summary": f"Could not validate: {exc.__class__.__name__}"})
            results.append(entry)
    return ToolOutput(
        data={
            "signatures": results,
            "count": len(results),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "Trusted means the certificate chains to a root in this server's trust store. "
            "Indian DSC roots (CCA India) may need to be added to the trust store to show as trusted.",
        }
    )
