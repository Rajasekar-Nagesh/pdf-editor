import base64
import datetime
import json
import re

import pymupdf as fitz
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from app.emailer import OUTBOX

from .conftest import make_png


def _cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Signer")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    pfx = pkcs12.serialize_key_and_certificates(b"t", key, cert, None, serialization.BestAvailableEncryption(b"pw"))
    return key, cert, pfx


def test_digital_signature_and_validation(client, guest, upload, run):
    _key, _cert_obj, pfx = _cert()
    f = upload(guest)
    r = client.post(
        "/api/sign/digital",
        headers=guest,
        data={"file_id": f["id"], "password": "wrong", "page": "0"},
        files={"certificate": ("me.pfx", pfx, "application/x-pkcs12")},
    )
    assert r.status_code == 400 and "password" in r.json()["detail"]

    r = client.post(
        "/api/sign/digital",
        headers=guest,
        data={"file_id": f["id"], "password": "pw", "page": "0", "rect": json.dumps([300, 700, 520, 780]), "reason": "Approved", "location": "Chennai"},
        files={"certificate": ("me.pfx", pfx, "application/x-pkcs12")},
    )
    assert r.status_code == 200, r.text
    signed = r.json()["file"]
    assert "Test Signer" in r.json()["signature"]["signer"]

    job = run(guest, "validate_signatures", [signed["id"]])
    sig = job["result"]["data"]["signatures"][0]
    assert sig["intact"] and sig["valid"] and not sig["trusted"]  # self-signed is not trusted


def test_usb_token_two_step_signing(client, guest, upload, run):
    key, cert, _ = _cert()
    f = upload(guest)
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    r = client.post("/api/sign/dsc/prepare", headers=guest, json={"file_id": f["id"], "certificate": cert_pem, "page": 0, "rect": [50, 700, 250, 780]})
    assert r.status_code == 200, r.text
    prep = r.json()
    # The "token" (here: a local key) signs the bytes on the user's computer.
    sig = key.sign(base64.b64decode(prep["to_sign"]), padding.PKCS1v15(), hashes.SHA256())
    r = client.post("/api/sign/dsc/complete", headers=guest, json={"state_token": prep["state_token"], "signature": base64.b64encode(sig).decode()})
    assert r.status_code == 200, r.text
    job = run(guest, "validate_signatures", [r.json()["file"]["id"]])
    assert job["result"]["data"]["signatures"][0]["intact"]

    bad = client.post("/api/sign/dsc/complete", headers=guest, json={"state_token": "x.y.z", "signature": "A" * 40})
    assert bad.status_code == 400


def _token_for(email: str) -> str:
    for msg in reversed(OUTBOX):
        if msg["To"] == email:
            return re.search(r"/sign/([\w-]+)", msg.get_content()).group(1)
    raise AssertionError(f"no email for {email}")


def test_send_for_signature_flow(client, user, upload, fetch):
    OUTBOX.clear()
    h = user["headers"]
    f = upload(h)
    body = {
        "file_id": f["id"],
        "title": "NDA",
        "message": "Please sign",
        "signers": [{"name": "Asha", "email": "asha@example.com", "order": 1}, {"name": "Bala", "email": "bala@example.com", "order": 2}],
    }
    r = client.post("/api/signature-requests", headers=h, json=body)
    assert r.status_code == 201
    req = r.json()
    assert [s["status"] for s in req["signers"]] == ["sent", "waiting"]
    assert [m["To"] for m in OUTBOX] == ["asha@example.com"]  # only the first in order is invited

    asha = _token_for("asha@example.com")
    view = client.get(f"/api/public/sign/{asha}").json()
    assert view["can_sign"] and view["title"] == "NDA"
    assert client.get(f"/api/public/sign/{asha}/document").content.startswith(b"%PDF")

    # Reminder issues a fresh link; the old one stops working.
    assert client.post(f"/api/signature-requests/{req['id']}/remind", headers=h).json()["sent"] == 1
    assert client.get(f"/api/public/sign/{asha}").status_code == 404
    asha = _token_for("asha@example.com")

    sig = "data:image/png;base64," + base64.b64encode(make_png()).decode()
    r = client.post(f"/api/public/sign/{asha}/sign", json={"image_data": sig, "placements": [{"page": 0, "rect": [300, 700, 450, 760]}]})
    assert r.status_code == 200 and r.json()["request_status"] == "pending"
    assert client.post(f"/api/public/sign/{asha}/sign", json={"image_data": sig, "placements": [{"page": 0, "rect": [1, 1, 50, 50]}]}).status_code == 400

    bala = _token_for("bala@example.com")
    r = client.post(f"/api/public/sign/{bala}/sign", json={"image_data": sig, "placements": [{"page": 0, "rect": [300, 600, 450, 660]}]})
    assert r.json()["request_status"] == "completed"

    req = client.get(f"/api/signature-requests/{req['id']}", headers=h).json()
    assert req["status"] == "completed" and req["audit_file_id"]
    actions = [e["action"] for e in req["events"]]
    assert actions[0] == "created" and "signed" in actions and actions[-1] == "completed"
    audit = fitz.open(stream=fetch(h, req["audit_file_id"]))
    assert "Signature Audit Trail" in audit[0].get_text() and "bala@example.com" in audit[0].get_text()
    final = fitz.open(stream=fetch(h, req["current_file_id"]))
    assert len(final[0].get_images()) == 3  # original image + two signatures
    assert client.get(f"/api/signature-requests/{req['id']}/files", headers=h).json()["audit"]
    assert client.get("/api/signature-requests", headers=h).json()["requests"]
    completion = [m for m in OUTBOX if m["Subject"].startswith("Completed")]
    assert completion and any(part.get_filename() for part in completion[0].iter_attachments())


def test_decline_and_cancel(client, user, upload):
    OUTBOX.clear()
    h = user["headers"]
    f = upload(h)
    body = {"file_id": f["id"], "title": "Lease", "signers": [{"name": "C", "email": "c@example.com"}]}
    req = client.post("/api/signature-requests", headers=h, json=body).json()
    token = _token_for("c@example.com")
    assert client.post(f"/api/public/sign/{token}/decline", json={"reason": "Wrong amount"}).status_code == 200
    req = client.get(f"/api/signature-requests/{req['id']}", headers=h).json()
    assert req["status"] == "declined"

    req2 = client.post("/api/signature-requests", headers=h, json=body).json()
    assert client.post(f"/api/signature-requests/{req2['id']}/cancel", headers=h).json()["status"] == "cancelled"
    assert client.post(f"/api/signature-requests/{req2['id']}/remind", headers=h).status_code == 400
    dup = {**body, "signers": [{"name": "C", "email": "c@example.com"}, {"name": "D", "email": "C@example.com"}]}
    assert client.post("/api/signature-requests", headers=h, json=dup).status_code == 400


def test_automatic_reminders(client, user, upload):
    from datetime import timedelta

    from app.db import SessionLocal
    from app.routers.signrequests import send_reminders_for

    OUTBOX.clear()
    h = user["headers"]
    f = upload(h)
    client.post("/api/signature-requests", headers=h, json={"file_id": f["id"], "title": "R", "signers": [{"name": "E", "email": "e@example.com"}]})
    with SessionLocal() as db:
        assert send_reminders_for(db, older_than=timedelta(seconds=-1)) >= 1
    assert any(m["Subject"].startswith("Reminder") for m in OUTBOX)
