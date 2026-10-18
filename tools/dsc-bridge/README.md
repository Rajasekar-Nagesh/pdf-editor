# PDFDesk USB DSC token bridge

Web pages cannot talk to USB tokens directly, so this tiny program runs on **your own computer** and lets
PDFDesk sign with your Class 3 DSC token (ePass2003, ProxKey, WatchData, mToken, SafeNet ...).

* The private key never leaves the token.
* The PIN is sent only to this program on `127.0.0.1`, never to the PDFDesk server.
* PDFDesk only receives the finished signature value.

## Install

1. Install the token driver from your token vendor (you probably already have it).
2. Install Python 3.10+ from https://www.python.org/downloads/ (tick "Add Python to PATH" on Windows).
3. Open a terminal / Command Prompt in this folder and run:

   ```
   pip install python-pkcs11 asn1crypto
   ```

## Run

```
python bridge.py --origin https://pdf.example.com
```

If the driver is not found automatically, pass its path:

| Token | Windows | Linux |
|---|---|---|
| ePass2003 | `C:\Windows\System32\eps2003csp11.dll` | `/usr/lib/libcastle.so.1.0.0` |
| ProxKey / WatchData | `C:\Windows\System32\SignatureP11.dll` | `/usr/lib/WatchData/ProxKey/lib/libwdpkcs_SignatureP11.so` |
| SafeNet eToken | `C:\Windows\System32\eTPKCS11.dll` | `/usr/lib/libeTPkcs11.so` |

```
python bridge.py --lib "C:\Windows\System32\eps2003csp11.dll" --origin https://pdf.example.com
```

Then in PDFDesk open **Digital signature → USB DSC token**, enter your PIN and click **Sign with USB token**.
