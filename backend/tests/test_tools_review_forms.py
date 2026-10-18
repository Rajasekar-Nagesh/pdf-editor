import pymupdf as fitz

from .conftest import make_pdf, make_png


def _doc(fetch, headers, job, idx=0):
    return fitz.open(stream=fetch(headers, job["result"]["files"][idx]["id"]))


def test_annotations(client, guest, upload, run, fetch):
    f = upload(guest)
    anns = [
        {"type": "highlight", "page": 0, "rect": [70, 55, 300, 80]},
        {"type": "underline", "page": 0, "rect": [70, 95, 300, 115]},
        {"type": "strikeout", "page": 0, "rect": [70, 125, 300, 145], "color": "#ff0000"},
        {"type": "note", "page": 0, "point": [400, 100], "text": "Please check"},
        {"type": "ink", "page": 0, "strokes": [[[100, 600], [120, 620], [150, 610]]]},
        {"type": "rect", "page": 0, "rect": [100, 650, 200, 700]},
        {"type": "circle", "page": 0, "rect": [220, 650, 300, 700], "fill": "#00ff00"},
        {"type": "arrow", "page": 0, "from": [320, 650], "to": [400, 700]},
        {"type": "textbox", "page": 0, "rect": [400, 720, 550, 780], "text": "Reviewed", "size": 11},
    ]
    job = run(guest, "annotate", [f["id"]], {"annotations": anns, "author": "Priya"})
    v = job["result"]["files"][0]["id"]
    listed = client.get(f"/api/files/{v}/inspect/annotations?page=0", headers=guest).json()["result"]
    assert len(listed) == len(anns) and all(a["author"] == "Priya" for a in listed)
    job = run(guest, "delete_annotation", [v], {"page": 0, "xref": listed[0]["xref"]})
    assert len(list(_doc(fetch, guest, job)[0].annots())) == len(anns) - 1
    assert run(guest, "annotate", [f["id"]], {"annotations": [{"type": "bogus", "page": 0}]}, expect="failed")["error"]


def test_compare(client, guest, upload, run, fetch):
    a = upload(guest, make_pdf(2, extra="The fee is 1000 rupees"))
    b = upload(guest, make_pdf(2, extra="The fee is 2500 rupees"))
    job = run(guest, "compare", [a["id"], b["id"]])
    data = job["result"]["data"]
    assert not data["identical"] and data["stats"]["replaced"] >= 1
    assert any("1000" in c["old"] and "2500" in c["new"] for c in data["changes"])
    assert len(job["result"]["files"]) == 3
    same = run(guest, "compare", [a["id"], a["id"]])
    assert same["result"]["data"]["identical"]


def test_forms_create_fill_detect(client, guest, upload, run, fetch):
    f = upload(guest)
    fields = [
        {"page": 0, "rect": [200, 95, 400, 115], "type": "text", "name": "full_name"},
        {"page": 0, "rect": [72, 200, 86, 214], "type": "checkbox", "name": "agree"},
        {"page": 0, "rect": [200, 230, 300, 250], "type": "dropdown", "name": "city", "options": ["Chennai", "Delhi"]},
        {"page": 0, "rect": [200, 260, 300, 280], "type": "date", "name": "dob"},
        {"page": 0, "rect": [72, 340, 86, 354], "type": "radio", "name": "plan", "value": "basic"},
    ]
    job = run(guest, "add_fields", [f["id"]], {"fields": fields})
    form_id = job["result"]["files"][0]["id"]
    listed = client.get(f"/api/files/{form_id}/inspect/fields", headers=guest).json()["result"]
    assert {x["name"] for x in listed} >= {"full_name", "agree", "city", "dob"}

    job = run(guest, "fill_form", [form_id], {"values": {"full_name": "Meena", "agree": True, "city": "Delhi"}})
    assert job["result"]["data"]["filled"] == 3
    d = _doc(fetch, guest, job)
    values = {w.field_name: w.field_value for w in d[0].widgets()}
    assert values["full_name"] == "Meena" and values["city"] == "Delhi"
    job = run(guest, "fill_form", [form_id], {"values": {"full_name": "Meena"}, "flatten": True})
    assert not list(_doc(fetch, guest, job)[0].widgets())
    run(guest, "delete_field", [form_id], {"name": "city"})
    assert run(guest, "fill_form", [f["id"]], {"values": {}}, expect="failed")["error"]

    job = run(guest, "prepare_form", [f["id"]])
    assert job["result"]["data"]["count"] >= 3  # underscores, drawn box, signature line on each page
    types = {c["type"] for c in job["result"]["data"]["created"]}
    assert {"text", "checkbox"} <= types


def test_place_signature(client, guest, upload, run, fetch):
    import base64

    f = upload(guest)
    data = "data:image/png;base64," + base64.b64encode(make_png()).decode()
    job = run(guest, "place_signature", [f["id"]], {"image_data": data, "placements": [{"page": 0, "rect": [300, 700, 450, 760]}]})
    assert len(_doc(fetch, guest, job)[0].get_images()) == 2
    img = upload(guest, make_png(), "sig.png", "image/png")
    run(guest, "place_signature", [f["id"]], {"image_file_id": img["id"], "placements": [{"page": 1, "rect": [300, 700, 450, 760]}]})
    assert run(guest, "place_signature", [f["id"]], {"image_data": "data:image/png;base64,aGVsbG8=", "placements": [{"page": 0, "rect": [0, 0, 10, 10]}]}, expect="failed")["error"]
