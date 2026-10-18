import io

import pikepdf
import pymupdf as fitz

from app.config import get_settings
from app.services import ai as ai_service

from .conftest import make_pdf, make_png


def test_accessibility_check_and_autotag(client, guest, upload, run, fetch):
    f = upload(guest)
    job = run(guest, "accessibility_check", [f["id"]])
    items = {i["id"]: i["status"] for i in job["result"]["data"]["items"]}
    assert items["tagged"] == "fail" and items["lang"] == "fail"

    job = run(guest, "auto_tag", [f["id"]], {"language": "en-IN", "title": "Test document", "alt_text": "Red square"})
    tagged_id = job["result"]["files"][0]["id"]
    with pikepdf.open(io.BytesIO(fetch(guest, tagged_id))) as pdf:
        assert "/StructTreeRoot" in pdf.Root and str(pdf.Root.Lang) == "en-IN"
    job = run(guest, "accessibility_check", [tagged_id])
    items = {i["id"]: i["status"] for i in job["result"]["data"]["items"]}
    assert items["tagged"] == "pass" and items["lang"] == "pass" and items["order"] == "pass" and items["alt"] == "pass"
    assert run(guest, "auto_tag", [f["id"]], {"language": "not a language!"}, expect="failed")["error"]


def test_preflight(client, guest, upload, run):
    f = upload(guest)
    job = run(guest, "preflight", [f["id"]], {"min_dpi": 300, "require_cmyk": True})
    checks = {c["id"]: c for c in job["result"]["data"]["checks"]}
    assert checks["resolution"]["status"] == "warn"  # 40px image over 80pt = 36 dpi
    assert checks["fonts"]["status"] in ("pass", "fail")
    assert job["result"]["data"]["images"]


def test_batch_and_workflows(client, user, upload, run, fetch):
    h = user["headers"]
    a, b = upload(h), upload(h, make_pdf(2))
    steps = [
        {"tool": "watermark", "params": {"text": "DRAFT"}},
        {"tool": "page_numbers", "params": {"template": "{n}/{total}"}},
        {"tool": "set_metadata", "params": {"title": "Batch"}},
    ]
    r = client.post("/api/workflows", headers=h, json={"name": "Stamp it", "steps": steps})
    assert r.status_code == 201
    wf = r.json()
    assert client.get("/api/workflows", headers=h).json()["workflows"][0]["id"] == wf["id"]

    r = client.put(f"/api/workflows/{wf['id']}", headers=h, json={"name": "Stamp it v2", "steps": steps})
    assert r.json()["name"] == "Stamp it v2"
    assert client.post("/api/workflows", headers=h, json={"name": "x", "steps": [{"tool": "merge"}]}).status_code == 400
    assert client.post(
        "/api/workflows", headers=h, json={"name": "x", "steps": [{"tool": "watermark", "params": {"password": "a"}}]}
    ).status_code == 400

    r = client.post(f"/api/workflows/{wf['id']}/run", headers=h, json={"file_ids": [a["id"], b["id"]]})
    job = client.get(f"/api/jobs/{r.json()['id']}", headers=h).json()
    assert job["status"] == "done" and job["result"]["zip"]
    d = fitz.open(stream=fetch(h, job["result"]["files"][1]["id"]))
    assert "DRAFT" in d[0].get_text() and "1/2" in d[0].get_text() and d.metadata["title"] == "Batch"

    # Unsaved batch via the tools endpoint, with an image input converted first.
    img = upload(h, make_png(), "scan.png", "image/png")
    job = run(h, "batch", [img["id"]], {"steps": [{"tool": "rotate", "params": {"angle": 90}}]})
    assert job["result"]["files"][0]["name"] == "scan.pdf"

    assert client.delete(f"/api/workflows/{wf['id']}", headers=h).status_code == 204
    assert client.get("/api/workflows", headers={"X-Guest-Token": "g" * 20}).status_code == 401
    assert client.get("/api/jobs", headers=h).json()["jobs"]


def test_ai_disabled(client, guest, upload):
    assert client.get("/api/ai/status").json() == {"enabled": False}
    f = upload(guest)
    assert client.post("/api/ai/summary", headers=guest, json={"file_id": f["id"]}).status_code == 503


def test_ai_enabled_with_fake_llm(client, guest, upload, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    captured = {}

    def fake_call(messages):
        captured["messages"] = messages
        return "The document greets the reader [p. 1] and repeats on later pages [pp. 2-3]."

    monkeypatch.setattr(ai_service, "_call", fake_call)
    f = upload(guest)
    assert client.get("/api/ai/status").json()["enabled"] is True
    r = client.post("/api/ai/summary", headers=guest, json={"file_id": f["id"]})
    assert r.status_code == 200 and r.json()["citations"] == [1, 2, 3]
    assert '<page number="1">' in captured["messages"][0]["content"]

    r = client.post(
        "/api/ai/chat",
        headers=guest,
        json={"file_id": f["id"], "messages": [{"role": "user", "content": "What is the PAN?"}]},
    )
    assert r.status_code == 200 and r.json()["answer"]
    r = client.post("/api/ai/chat", headers=guest, json={"file_id": f["id"], "messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 400


def test_ai_page_selection_for_long_documents():
    texts = [f"filler text page {i} " * 50 for i in range(30)]
    texts[17] += " invoice total amount due rupees"
    chosen = ai_service._select_pages(texts, "what is the invoice total", budget=3000)
    assert 0 in chosen and 17 in chosen and len(chosen) < 30
