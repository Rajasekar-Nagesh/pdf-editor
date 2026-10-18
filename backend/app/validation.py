"""Upload validation based on the actual file content (magic bytes), not the file name."""
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


class InvalidFile(ValueError):
    pass


@dataclass
class FileType:
    kind: str  # pdf, docx, xlsx, pptx, doc, xls, ppt, odt, ods, odp, image
    mime: str
    ext: str


OOXML = {
    "word/": FileType("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
    "xl/": FileType("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "ppt/": FileType("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"),
}
ODF = {
    "application/vnd.oasis.opendocument.text": FileType("odt", "application/vnd.oasis.opendocument.text", "odt"),
    "application/vnd.oasis.opendocument.spreadsheet": FileType("ods", "application/vnd.oasis.opendocument.spreadsheet", "ods"),
    "application/vnd.oasis.opendocument.presentation": FileType(
        "odp", "application/vnd.oasis.opendocument.presentation", "odp"
    ),
}
IMAGE_FORMATS = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "BMP": "bmp", "TIFF": "tiff", "WEBP": "webp"}
OFFICE_KINDS = {"docx", "xlsx", "pptx", "doc", "xls", "ppt", "odt", "ods", "odp"}


def _sniff_ole(path: Path, name_hint: str) -> FileType:
    """Legacy MS Office (OLE2 compound file). Distinguish by inner stream names."""
    data = path.read_bytes()[: 2 * 1024 * 1024]
    hint = name_hint.lower()
    if b"W\x00o\x00r\x00d\x00D\x00o\x00c\x00u\x00m\x00e\x00n\x00t" in data or hint.endswith(".doc"):
        return FileType("doc", "application/msword", "doc")
    if b"W\x00o\x00r\x00k\x00b\x00o\x00o\x00k" in data or hint.endswith(".xls"):
        return FileType("xls", "application/vnd.ms-excel", "xls")
    if b"P\x00o\x00w\x00e\x00r\x00P\x00o\x00i\x00n\x00t" in data or hint.endswith(".ppt"):
        return FileType("ppt", "application/vnd.ms-powerpoint", "ppt")
    raise InvalidFile("Unrecognised legacy Office file.")


def sniff(path: Path, name_hint: str = "") -> FileType:
    """Detect the file type from its bytes. Raises InvalidFile if not an allowed type."""
    with open(path, "rb") as fh:
        head = fh.read(1024)
    if not head:
        raise InvalidFile("The file is empty.")

    # PDF: the header may be preceded by a little junk, which readers tolerate.
    if b"%PDF-" in head:
        return FileType("pdf", "application/pdf", "pdf")

    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return _sniff_ole(path, name_hint)

    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if "mimetype" in names:
                    mt = zf.read("mimetype").decode(errors="ignore").strip()
                    if mt in ODF:
                        return ODF[mt]
                if "[Content_Types].xml" in names:
                    for prefix, ft in OOXML.items():
                        if any(n.startswith(prefix) for n in names):
                            return ft
        except zipfile.BadZipFile as exc:
            raise InvalidFile("Corrupt archive.") from exc
        raise InvalidFile("Only PDF, Office documents and images are allowed.")

    try:
        with Image.open(path) as img:
            fmt = img.format
            img.verify()
        if fmt in IMAGE_FORMATS:
            ext = IMAGE_FORMATS[fmt]
            return FileType("image", Image.MIME.get(fmt, f"image/{ext}"), ext)
    except Exception:
        pass
    raise InvalidFile("Only PDF, Office documents (Word, Excel, PowerPoint) and images are allowed.")


def sniff_bytes(data: bytes, name_hint: str = "") -> FileType:
    import tempfile

    with tempfile.NamedTemporaryFile() as tmp:
        tmp.write(data)
        tmp.flush()
        return sniff(Path(tmp.name), name_hint)


def is_image_bytes(data: bytes) -> bool:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        return True
    except Exception:
        return False
