import io

import pymupdf as fitz

from .conftest import make_pdf, make_png


def _doc(fetch, headers, job, idx=0):
    return fitz.open(stream=fetch(headers, job["result"]["files"][idx]["id"]))


def test_tool_catalog(client):
    tools = {t["name"] for t in client.get("/api/tools").json()["tools"]}
    assert {"merge", "split", "ocr", "redact", "compare", "batch", "to_pdfa"} <= tools


def test_unknown_tool_and_bad_counts(client, guest, upload):
    f = upload(guest)
    assert client.post("/api/tools/nope", headers=guest, json={"file_ids": [f["id"]]}).status_code == 404
    assert client.post("/api/tools/merge", headers=guest, json={"file_ids": [f["id"]]}).status_code == 400
    assert client.get("/api/jobs/doesnotexist", headers=guest).status_code == 404


def test_unknown_param_is_friendly(client, guest, upload, run):
    f = upload(guest)
    job = run(guest, "rotate", [f["id"]], {"bogus": 1}, expect="failed")
    assert "Unexpected option" in job["error"]


def test_reorder_rotate_delete_extract_insert_crop(client, guest, upload, run, fetch):
    f = upload(guest)
    job = run(guest, "reorder", [f["id"]], {"order": [3, 1, 2]})
    d = _doc(fetch, guest, job)
    assert "page 3" in d[0].get_text()
    assert job["result"]["files"][0]["parent_id"] == f["id"]  # versioned for undo

    d = _doc(fetch, guest, run(guest, "rotate", [f["id"]], {"pages": "1", "angle": 90}))
    assert d[0].rotation == 90 and d[1].rotation == 0

    assert _doc(fetch, guest, run(guest, "delete_pages", [f["id"]], {"pages": "2-3"})).page_count == 1
    assert run(guest, "delete_pages", [f["id"]], {"pages": "all"}, expect="failed")["error"]
    assert _doc(fetch, guest, run(guest, "extract_pages", [f["id"]], {"pages": "2,3"})).page_count == 2
    assert _doc(fetch, guest, run(guest, "insert_blank", [f["id"]], {"after": 1, "count": 2})).page_count == 5

    d = _doc(fetch, guest, run(guest, "crop", [f["id"]], {"left": 50, "top": 50, "right": 50, "bottom": 50}))
    assert round(d[0].rect.width) == 495
    d = _doc(fetch, guest, run(guest, "crop", [f["id"]], {"rect": [0, 0, 300, 400], "pages": "1"}))
    assert round(d[0].rect.width) == 300


def test_merge_and_split(client, guest, upload, run, fetch):
    a, b = upload(guest), upload(guest, make_pdf(2))
    img = upload(guest, make_png(), "p.png", "image/png")
    d = _doc(fetch, guest, run(guest, "merge", [a["id"], b["id"], img["id"]]))
    assert d.page_count == 6

    job = run(guest, "split", [a["id"]], {"mode": "every", "every": 1})
    assert len(job["result"]["files"]) == 3 and job["result"]["zip"] is not None
    job = run(guest, "split", [a["id"]], {"mode": "ranges", "ranges": "1-2; 3"})
    assert len(job["result"]["files"]) == 2
    assert "Invalid page range" in run(guest, "split", [a["id"]], {"mode": "ranges", "ranges": "x-y"}, expect="failed")["error"]


def test_text_editing(client, guest, upload, run, fetch):
    f = upload(guest)
    spans = client.get(f"/api/files/{f['id']}/inspect/spans?page=0", headers=guest).json()["result"]
    s = next(s for s in spans if "Hello PDFDesk" in s["text"])
    job = run(
        guest,
        "replace_text",
        [f["id"]],
        {"page": 0, "bbox": s["bbox"], "new_text": "Goodbye World", "font": s["font"], "size": s["size"], "color": s["color"], "origin": s["origin"]},
    )
    text = _doc(fetch, guest, job)[0].get_text()
    assert "Goodbye World" in text and "Hello PDFDesk" not in text

    job = run(guest, "add_text", [f["id"]], {"page": 1, "x": 100, "y": 600, "text": "Added line\nSecond", "size": 12, "color": "#0000ff"})
    assert "Added line" in _doc(fetch, guest, job)[1].get_text()
    # Tamil text falls back to a Unicode font when available, and must not crash.
    run(guest, "add_text", [f["id"]], {"page": 0, "x": 100, "y": 650, "text": "வணக்கம்"})


def test_image_operations(client, guest, upload, run, fetch):
    f = upload(guest)
    img = upload(guest, make_png(), "logo.png", "image/png")
    job = run(guest, "add_image", [f["id"]], {"page": 0, "rect": [50, 500, 170, 560], "image_file_id": img["id"]})
    assert len(_doc(fetch, guest, job)[0].get_images()) == 2

    xref = client.get(f"/api/files/{f['id']}/inspect/images?page=0", headers=guest).json()["result"][0]["xref"]
    run(guest, "replace_image", [f["id"]], {"page": 0, "xref": xref, "image_file_id": img["id"]})
    job = run(guest, "move_image", [f["id"]], {"page": 0, "xref": xref, "rect": [100, 100, 300, 300]})
    info = _doc(fetch, guest, job)[0].get_image_info()
    assert any(abs(i["bbox"][0] - 100) < 1 for i in info)
    run(guest, "crop_image", [f["id"]], {"page": 0, "xref": xref, "left": 0.1, "right": 0.1})
    job = run(guest, "delete_image", [f["id"]], {"page": 0, "xref": xref})
    assert _doc(fetch, guest, job)[0].get_image_info() == []
    assert run(guest, "delete_image", [f["id"]], {"page": 0, "xref": 99999}, expect="failed")["error"]


def test_links_bookmarks_attachments(client, guest, upload, run, fetch):
    f = upload(guest)
    job = run(guest, "set_link", [f["id"]], {"page": 0, "rect": [72, 60, 200, 80], "uri": "example.com"})
    v1 = job["result"]["files"][0]["id"]
    links = client.get(f"/api/files/{v1}/inspect/links?page=0", headers=guest).json()["result"]
    assert links[0]["uri"] == "https://example.com"
    job = run(guest, "set_link", [v1], {"page": 0, "index": 0, "target_page": 3})
    v2 = job["result"]["files"][0]["id"]
    assert client.get(f"/api/files/{v2}/inspect/links?page=0", headers=guest).json()["result"][0]["page"] == 3
    job = run(guest, "set_link", [v2], {"page": 0, "index": 0, "delete": True})
    assert client.get(f"/api/files/{job['result']['files'][0]['id']}/inspect/links?page=0", headers=guest).json()["result"] == []

    job = run(guest, "set_bookmarks", [f["id"]], {"items": [{"level": 1, "title": "Intro", "page": 1}, {"level": 2, "title": "Part", "page": 2}]})
    assert _doc(fetch, guest, job).get_toc() == [[1, "Intro", 1], [2, "Part", 2]]

    att = upload(guest, make_png(), "receipt.png", "image/png")
    job = run(guest, "add_attachment", [f["id"]], {"attachment_file_id": att["id"], "description": "Receipt"})
    v = job["result"]["files"][0]["id"]
    names = client.get(f"/api/files/{v}/inspect/attachments", headers=guest).json()["result"]
    assert names[0]["name"] == "receipt.png"
    job = run(guest, "remove_attachment", [v], {"name": "receipt.png"})
    assert _doc(fetch, guest, job).embfile_count() == 0


def test_flatten_and_metadata(client, guest, upload, run, fetch):
    f = upload(guest)
    job = run(guest, "annotate", [f["id"]], {"annotations": [{"type": "note", "page": 0, "point": [300, 300], "text": "Check"}]})
    annotated = job["result"]["files"][0]["id"]
    job = run(guest, "flatten", [annotated])
    assert list(_doc(fetch, guest, job)[0].annots()) == []
    job = run(guest, "set_metadata", [f["id"]], {"title": "Contract", "author": "Ravi", "keywords": "legal, nda"})
    meta = _doc(fetch, guest, job).metadata
    assert meta["title"] == "Contract" and meta["author"] == "Ravi"


def test_stamps_and_bates(client, guest, upload, run, fetch):
    f = upload(guest)
    img = upload(guest, make_png(), "wm.png", "image/png")
    assert "CONFIDENTIAL" in _doc(fetch, guest, run(guest, "watermark", [f["id"]], {"text": "CONFIDENTIAL"}))[0].get_text()
    run(guest, "watermark", [f["id"]], {"image_file_id": img["id"], "layout": "tile", "opacity": 0.3})
    assert run(guest, "watermark", [f["id"]], {}, expect="failed")["error"]
    d = _doc(fetch, guest, run(guest, "page_numbers", [f["id"]], {"template": "Page {n} of {total}", "position": "bottom-right"}))
    assert "Page 2 of 3" in d[1].get_text()
    d = _doc(fetch, guest, run(guest, "header_footer", [f["id"]], {"header_center": "ACME Ltd", "footer_left": "{filename}"}))
    assert "ACME Ltd" in d[0].get_text()

    g = upload(guest, make_pdf(2))
    job = run(guest, "bates", [f["id"], g["id"]], {"prefix": "ABC", "start": 100, "digits": 5})
    second = _doc(fetch, guest, job, 1)
    assert "ABC00104" in second[1].get_text()
    assert job["result"]["data"]["last"] == 104
