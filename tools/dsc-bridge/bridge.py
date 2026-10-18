#!/usr/bin/env python3
"""PDFDesk USB DSC token bridge.

Runs on the signer's own computer (Windows, macOS or Linux) and lets the PDFDesk web page sign with a
USB Digital Signature Certificate token (ePass2003, ProxKey, WatchData, mToken, SafeNet ...) through the
token's PKCS#11 driver. The private key never leaves the token, and the PIN never leaves this computer.

    pip install python-pkcs11 asn1crypto
    python bridge.py --lib "C:\\Windows\\System32\\eps2003csp11.dll" --origin https://pdf.example.com

Endpoints (localhost only):
    GET  /certificate  -> {"certificate": "<PEM>", "subject": "..."}
    POST /sign  {"data": "<base64>", "digest": "sha256", "pin": "1234"} -> {"signature": "<base64>"}
"""
import argparse
import base64
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import pkcs11
    from pkcs11 import Attribute, Mechanism, ObjectClass
    from pkcs11.exceptions import PinIncorrect, PinLenRange
except ImportError:  # pragma: no cover - friendly message for end users
    sys.exit("Please install the dependencies first:  pip install python-pkcs11 asn1crypto")
from asn1crypto import pem, x509

# Common PKCS#11 driver locations for tokens used in India. Pass --lib if yours is elsewhere.
KNOWN_LIBS = [
    r"C:\Windows\System32\eps2003csp11.dll",  # ePass2003
    r"C:\Windows\System32\SignatureP11.dll",  # ProxKey / WatchData
    r"C:\Windows\System32\eTPKCS11.dll",  # SafeNet eToken
    r"C:\Windows\System32\CryptoIDA_pkcs11.dll",  # mToken CryptoID
    "/usr/lib/libcastle.so.1.0.0",  # ePass2003 (Linux)
    "/usr/lib/WatchData/ProxKey/lib/libwdpkcs_SignatureP11.so",
    "/usr/lib/libeTPkcs11.so",
    "/Library/Frameworks/eToken.framework/Versions/A/libeToken.dylib",
    "/usr/local/lib/libcastle.1.0.0.dylib",
]

LOCK = threading.Lock()


def find_lib(path: str | None) -> str:
    import os

    if path:
        return path
    for candidate in KNOWN_LIBS:
        if os.path.exists(candidate):
            return candidate
    sys.exit("Could not find your token's PKCS#11 driver. Start the bridge with --lib <path to driver>.")


class Token:
    def __init__(self, lib_path: str, slot_index: int):
        self.lib = pkcs11.lib(lib_path)
        slots = self.lib.get_slots(token_present=True)
        if not slots:
            raise RuntimeError("No USB token detected. Plug in your DSC token and try again.")
        self.token = slots[min(slot_index, len(slots) - 1)].get_token()

    def certificate(self) -> x509.Certificate:
        with self.token.open() as session:
            for obj in session.get_objects({Attribute.CLASS: ObjectClass.CERTIFICATE}):
                cert = x509.Certificate.load(obj[Attribute.VALUE])
                # Prefer a certificate usable for signing (non-repudiation / digital signature).
                ku = cert.key_usage_value
                if ku is None or "digital_signature" in ku.native or "non_repudiation" in ku.native:
                    return cert
        raise RuntimeError("No signing certificate found on the token.")

    def sign(self, data: bytes, pin: str) -> bytes:
        cert = self.certificate()
        with self.token.open(user_pin=pin) as session:
            keys = list(session.get_objects({Attribute.CLASS: ObjectClass.PRIVATE_KEY}))
            if not keys:
                raise RuntimeError("No private key found on the token.")
            key = keys[0]
            algo = cert.public_key.algorithm
            if algo == "rsa":
                return key.sign(data, mechanism=Mechanism.SHA256_RSA_PKCS)
            if algo == "ec":
                from pkcs11.util.ec import encode_ecdsa_signature

                return encode_ecdsa_signature(key.sign(data, mechanism=Mechanism.ECDSA_SHA256))
            raise RuntimeError(f"Unsupported key type: {algo}")


def make_handler(token: Token, origin: str):
    class Handler(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            # Chrome "Private Network Access": allow an HTTPS site to call this localhost service.
            self.send_header("Access-Control-Allow-Private-Network", "true")

        def _json(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _allowed(self) -> bool:
            req_origin = self.headers.get("Origin")
            if origin != "*" and req_origin and req_origin != origin:
                self._json(403, {"error": "This site is not allowed to use the signing bridge."})
                return False
            return True

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if not self._allowed():
                return
            if self.path != "/certificate":
                return self._json(404, {"error": "Not found"})
            try:
                with LOCK:
                    cert = token.certificate()
                pem_text = pem.armor("CERTIFICATE", cert.dump()).decode()
                self._json(200, {"certificate": pem_text, "subject": cert.subject.human_friendly})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def do_POST(self):
            if not self._allowed():
                return
            if self.path != "/sign":
                return self._json(404, {"error": "Not found"})
            try:
                length = min(int(self.headers.get("Content-Length", 0)), 1_000_000)
                body = json.loads(self.rfile.read(length) or b"{}")
                if body.get("digest", "sha256") != "sha256":
                    return self._json(400, {"error": "Only SHA-256 is supported."})
                data = base64.b64decode(body["data"])
                with LOCK:
                    signature = token.sign(data, str(body.get("pin", "")))
                self._json(200, {"signature": base64.b64encode(signature).decode()})
            except (PinIncorrect, PinLenRange):
                self._json(401, {"error": "Incorrect token PIN."})
            except Exception as exc:
                self._json(500, {"error": str(exc)})

        def log_message(self, fmt, *args):  # never log request bodies (they contain the PIN)
            sys.stderr.write(f"{self.address_string()} {self.command} {self.path}\n")

    return Handler


def main():
    ap = argparse.ArgumentParser(description="PDFDesk USB DSC token signing bridge")
    ap.add_argument("--lib", help="Path to the token's PKCS#11 driver (.dll / .so / .dylib)")
    ap.add_argument("--origin", default="*", help="Your PDFDesk address, e.g. https://pdf.example.com (recommended)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--slot", type=int, default=0, help="Token slot index if several tokens are plugged in")
    args = ap.parse_args()

    token = Token(find_lib(args.lib), args.slot)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(token, args.origin))
    print(f"PDFDesk DSC bridge running on http://127.0.0.1:{args.port} (allowed origin: {args.origin}). Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
