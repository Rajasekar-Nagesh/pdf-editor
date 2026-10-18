"""Test configuration: SQLite + local storage + synchronous jobs, so no Docker services are needed."""
import io
import os
import shutil
import tempfile
import uuid

TMP = tempfile.mkdtemp(prefix="pdfdesk-test-")
os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": f"sqlite:///{TMP}/test.db",
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_DIR": f"{TMP}/files",
        "JOB_MODE": "sync",
        "JWT_SECRET": "test-secret-key-that-is-long-enough-123",
        "RATE_LIMIT_PER_MINUTE": "100000",
        "RATE_LIMIT_AUTH_PER_MINUTE": "100000",
        "PUBLIC_URL": "http://testserver",
        "ANTHROPIC_API_KEY": "",
    }
)

import pymupdf as fitz  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.main import app  # noqa: E402


def need(binary: str):
    return pytest.mark.skipif(shutil.which(binary) is None, reason=f"{binary} not installed")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def guest():
    return {"X-Guest-Token": uuid.uuid4().hex}


@pytest.fixture
def user(client):
    email = f"u{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/api/auth/signup", json={"email": email, "password": "correct-horse-1", "name": "Test User"})
    assert r.status_code == 201, r.text
    data = r.json()
    return {"headers": {"Authorization": f"Bearer {data['token']}"}, "email": email, "id": data["user"]["id"]}


def make_pdf(pages: int = 3, text: str = "Hello PDFDesk", extra: str = "") -> bytes:
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 72), f"{text} page {i + 1}", fontsize=14)
        p.insert_text((72, 110), "Name: ____________", fontsize=12)
        p.insert_text((72, 140), "Contact rajesh@example.com PAN ABCDE1234F phone 9876543210", fontsize=10)
        if extra:
            p.insert_text((72, 170), extra, fontsize=11)
        p.draw_rect(fitz.Rect(72, 200, 86, 214), color=(0, 0, 0))
        p.insert_text((92, 212), "I agree", fontsize=11)
        p.draw_line((72, 300), (300, 300))
        p.insert_text((72, 320), "Signature", fontsize=10)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
        pix.set_rect(pix.irect, (200, 30, 30))
        p.insert_image(fitz.Rect(400, 400, 480, 480), pixmap=pix)
    return doc.tobytes()


def make_png(color=(30, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 60), color).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def upload(client):
    def _upload(headers, data: bytes | None = None, name: str = "doc.pdf", mime: str = "application/pdf"):
        r = client.post("/api/files", headers=headers, files={"files": (name, data if data is not None else make_pdf(), mime)})
        assert r.status_code == 201, r.text
        return r.json()["files"][0]

    return _upload


@pytest.fixture
def run(client):
    def _run(headers, tool, file_ids, params=None, expect="done"):
        r = client.post(f"/api/tools/{tool}", headers=headers, json={"file_ids": file_ids, "params": params or {}})
        assert r.status_code == 202, r.text
        job = r.json()
        # Jobs run synchronously in tests; poll endpoint anyway to exercise it.
        job = client.get(f"/api/jobs/{job['id']}", headers=headers).json()
        assert job["status"] == expect, job.get("error")
        return job

    return _run


@pytest.fixture
def fetch(client):
    def _fetch(headers, file_id) -> bytes:
        r = client.get(f"/api/files/{file_id}/download", headers=headers)
        assert r.status_code == 200
        return r.content

    return _fetch
