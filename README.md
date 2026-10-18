# PDFDesk

PDFDesk is a web-based PDF toolkit that works like Adobe Acrobat Pro in the browser. You can view, organize, edit,
annotate, compare, fill forms, sign (simple, certificate or USB DSC token), send for signature, convert, run OCR
(English, Tamil and Hindi), compress, protect, redact, sanitize, automate in batches, check accessibility and
print readiness, and chat with your PDF using AI.

* **Frontend:** React, Vite, TypeScript and Tailwind CSS, with pdf.js for viewing and pdf-lib for in-browser page editing
* **Backend:** Python FastAPI, PyMuPDF, pikepdf, OCRmyPDF/Tesseract, Ghostscript, LibreOffice, pdfplumber/Camelot,
  pyHanko, Playwright/Chromium and veraPDF
* **Infrastructure:** RQ background workers on Redis, PostgreSQL, S3-compatible storage (MinIO), Nginx and Let's Encrypt,
  all run with Docker Compose

---

## Contents

1. [Features](#features)
2. [Folder structure](#folder-structure)
3. [How it works](#how-it-works)
4. [Local setup (step by step)](#local-setup-step-by-step)
5. [Deploying on AWS Lightsail](#deploying-on-aws-lightsail)
6. [Updating the app](#updating-the-app)
7. [Backups](#backups)
8. [Security notes](#security-notes)
9. [Running the tests](#running-the-tests)
10. [Troubleshooting](#troubleshooting)

---

## Features

| Area | Tools |
|---|---|
| View & organize | Viewer with drag-and-drop upload, thumbnails, zoom and search. Organize pages in the browser (drag to reorder, rotate, delete, duplicate, insert blank, extract) with pdf-lib. Rotate, delete, extract, insert blank, crop, merge and split (by ranges or every N pages) |
| Edit | Click existing text to replace it (matching font and size, with Tamil and Hindi support) and add new text. Add, replace, move, resize, crop and delete images. Hyperlinks, bookmarks and file attachments. Flatten, metadata, watermark (text or image), page numbers, headers and footers, Bates numbering |
| Review | Highlight, underline, strikethrough, sticky notes, freehand drawing, boxes, ellipses, arrows and text boxes. Side-by-side compare with highlighted differences. Shareable review links where anyone can comment without an account (comments sync live) |
| Forms & signatures | Detect and fill fields. Create text, checkbox, radio, dropdown and date fields. Prepare Form auto-detects blanks and boxes. Simple signatures (draw, type or upload). Digital signatures with a .pfx/.p12 certificate or USB DSC token (pyHanko), including a visible signature block and signature validation. Send for signature with signing order, status tracking, reminders and an audit trail PDF |
| Convert | PDF to Word, Excel (tables kept), PowerPoint, PNG/JPG, HTML and text. Word, Excel, PowerPoint and images to PDF. Web page URL to PDF. PDF/A-2b with veraPDF validation. Compression (low, medium or high) with before and after sizes |
| Scan & OCR | Searchable PDFs (English, Tamil, Hindi). Scanned invoice and bill tables to Excel |
| Protect | Add or remove a password and restrict print, copy and edit. Redaction by area, search term or regex preset (PAN, GSTIN, Aadhaar, phone, email). Sanitize (hidden text, metadata, comments, attachments, JavaScript) |
| Automate & check | Saved batch actions (for example OCR, then compress, then watermark) run on many files, with the results in a ZIP. Accessibility check and auto-tag. Print preflight. Measure tool for distance and area with a custom scale |
| AI | Chat with your PDF and one-click summaries with clickable page citations. The AI tools are hidden when no API key is set |
| Accounts | Sign up, log in, password reset by email, saved documents, recent files, saved batch actions, a signature-requests dashboard and review links |

Other behavior:

* Every edit creates a new version, so **undo and redo** work across all tools.
* Long jobs show **progress bars**.
* The app works in **light and dark mode** and on desktop and mobile screens.

---

## Folder structure

```
pdf-editor/
├── .env.example                  # all settings (copy to .env)
├── docker-compose.yml            # nginx, api, worker, scheduler, db, redis, minio, certbot
├── README.md
├── backend/
│   ├── Dockerfile                # Python + Ghostscript, Tesseract (eng/tam/hin), LibreOffice, veraPDF, Chromium
│   ├── verapdf-auto-install.xml
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── app/
│   │   ├── main.py               # FastAPI app, middleware, error handlers
│   │   ├── config.py             # settings from environment variables
│   │   ├── db.py, models.py      # SQLAlchemy engine and tables
│   │   ├── schemas.py            # request bodies
│   │   ├── security.py           # bcrypt, JWT, guest identity
│   │   ├── storage.py            # S3/MinIO or local disk
│   │   ├── filestore.py          # uploads (content-checked), ownership, versions
│   │   ├── validation.py         # magic-byte file type detection
│   │   ├── ratelimit.py          # per-IP rate limiting (Redis)
│   │   ├── emailer.py            # SMTP
│   │   ├── jobs.py               # job creation/execution (RQ)
│   │   ├── worker.py             # `python -m app.worker`
│   │   ├── scheduler.py          # guest-file cleanup + signature reminders
│   │   ├── tools_registry.py     # every tool: inputs, queue/inline, batchable
│   │   ├── routers/              # auth, files, tools+jobs+workflows, sign, signrequests, review, ai
│   │   └── services/             # the PDF engines (pages, edit, stamp, annotate, compare, forms,
│   │                             #   signature, convert, optimize, protect, checks, inspect, ai, audit)
│   └── tests/                    # pytest suite covering every API endpoint
├── frontend/
│   ├── Dockerfile                # builds the SPA, serves it with Nginx (also the HTTPS reverse proxy)
│   ├── nginx/                    # Nginx templates + entrypoint (auto HTTP/HTTPS, cert reload)
│   ├── package.json, vite.config.ts, tailwind.config.js, tsconfig.json, index.html
│   └── src/
│       ├── App.tsx, main.tsx, index.css
│       ├── lib/                  # api client, app context (auth/theme/toasts), pdf.js setup, tool catalog
│       ├── components/           # PdfViewer, Layout, SignaturePad, shared UI
│       ├── pages/                # Home, Editor, Auth, Dashboard, Public (review + signing)
│       └── panels/               # right-hand option panels for each tool
├── scripts/
│   ├── init-letsencrypt.sh       # first HTTPS certificate
│   ├── backup.sh / restore.sh    # database + files
│   └── update.sh                 # backup, pull, rebuild, restart
└── tools/dsc-bridge/             # small local program for USB DSC token signing
```

---

## How it works

```
Browser ──HTTPS──> Nginx ──/api──> FastAPI (api) ──enqueue──> Redis ──> RQ workers (OCR, LibreOffice, Ghostscript, ...)
                     │                 │   │                                  │
                     └── React app      │   └──────── PostgreSQL <─────────────┤
                                        └──────────── MinIO (files) <──────────┘
```

* **Uploads.** The API checks each file's real content by its magic bytes, so only PDF, Office and image files are
  accepted (100 MB maximum). The file is then stored in MinIO.
* **Jobs.** Every tool runs as a job. Heavy tools run in the **worker** containers so the API stays fast. The browser
  polls the job and shows its progress. External programs have timeouts: LibreOffice, Ghostscript, OCR, Chromium and
  veraPDF.
* **Secrets.** Password tools and certificate signing run **inside the request**. Their passwords and certificates are
  held in memory only and are never written to the database, Redis or disk.
* **Versions.** Each edit that produces a PDF stores a **new version** linked to the previous one. This is how undo and
  redo work.
* **Guests and accounts.** Guests get a random ID in their browser, and their files are **deleted after 1 hour** by the
  scheduler. Files of logged-in users are kept until the user deletes them.
* **Rate limits.** Requests are limited per IP in both Nginx and the API, with a stricter limit on login and sign-up.

---

## Local setup (step by step)

### Option A: Docker (easiest)

1. Install **Docker Desktop** from https://www.docker.com/products/docker-desktop/ (Windows, Mac) or Docker Engine
   on Linux.
2. Download the code:
   ```bash
   git clone https://github.com/rajasekar-nagesh/pdf-editor.git
   cd pdf-editor
   ```
3. Create your settings file:
   ```bash
   cp .env.example .env
   ```
   Open `.env` in a text editor and set:
   * `DOMAIN=localhost`, `PUBLIC_URL=http://localhost` and `CORS_ORIGINS=http://localhost`
   * `ENVIRONMENT=development`. While `SMTP_HOST` is empty, password-reset and signing emails are printed to the API
     log so you can click their links.
   * `JWT_SECRET`, `POSTGRES_PASSWORD` and `MINIO_ROOT_PASSWORD`: any long random values (`openssl rand -hex 32`)
4. Start everything. The first build downloads LibreOffice, Tesseract and Chromium, which takes 10–20 minutes:
   ```bash
   docker compose up -d --build
   ```
5. Open **http://localhost** in your browser.
6. To see logs, for example the emails printed in development mode:
   ```bash
   docker compose logs -f api worker
   ```
7. To stop: `docker compose down`. Your data stays in Docker volumes.

### Option B: Run the code directly (for developers)

You need Python 3.11+, Node.js 20+, and optionally Ghostscript, Tesseract (`tesseract-ocr-eng`, `-tam`, `-hin`),
LibreOffice and veraPDF for the tools that use them.

```bash
# Backend: synchronous jobs, SQLite and a local file folder, so no Redis, Postgres or MinIO is needed
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium          # only for "Web page to PDF"
export ENVIRONMENT=development JOB_MODE=sync STORAGE_BACKEND=local LOCAL_STORAGE_DIR=./data/files \
       DATABASE_URL=sqlite:///./data/pdfdesk.db JWT_SECRET=dev-secret-change-me PUBLIC_URL=http://localhost:5173
mkdir -p data
uvicorn app.main:app --reload --port 8000

# Frontend (in a second terminal)
cd frontend
npm install
npm run dev                           # http://localhost:5173 (proxies /api to :8000)
```

API documentation is available at http://localhost:8000/api/docs.

---

## Deploying on AWS Lightsail

### 1. Create the server

* In Lightsail, choose **Create instance**, then **Linux/Unix** and **OS Only: Ubuntu 24.04 LTS** (22.04 also works).
* **Recommended size: at least 4 GB RAM and 2 vCPUs** (the $24/month plan). OCR, LibreOffice, Chromium and veraPDF
  all run on the server. For heavy OCR or many users, use **8 GB RAM and 4 vCPUs**. 2 GB is not enough for all
  features.
* Under **Networking**, create a **static IP** and attach it to the instance.

### 2. Open the firewall (ports 80 and 443)

In the instance, open **Networking** and then **IPv4 Firewall**, and make sure these rules exist:

| Application | Protocol | Port |
|---|---|---|
| SSH | TCP | 22 |
| HTTP | TCP | 80 |
| HTTPS | TCP | 443 |

Add the same rules under **IPv6 Firewall** if you use IPv6.

### 3. Point your domain at the server

At your domain registrar (or in Lightsail **Domains & DNS**), create an **A record**:

```
Type: A    Name: pdf (or @ for the root domain)    Value: <your static IP>    TTL: 300
```

Wait until `ping pdf.yourdomain.com` shows your static IP.

### 4. Install Docker

Connect with SSH (the browser terminal in Lightsail or `ssh ubuntu@<ip>`) and run:

```bash
sudo apt-get update && sudo apt-get -y upgrade
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit        # log out and back in so the docker group applies
```

On a 4 GB server, add swap to cushion large OCR jobs:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### 5. Get the code and configure it

```bash
git clone https://github.com/rajasekar-nagesh/pdf-editor.git pdfdesk
cd pdfdesk
cp .env.example .env
nano .env
```

Set at least the following:

```
DOMAIN=pdf.yourdomain.com
PUBLIC_URL=https://pdf.yourdomain.com
CORS_ORIGINS=https://pdf.yourdomain.com
ENVIRONMENT=production
JWT_SECRET=<output of: openssl rand -hex 32>
POSTGRES_PASSWORD=<random>
MINIO_ROOT_PASSWORD=<random>
LETSENCRYPT_EMAIL=you@yourdomain.com
SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM="PDFDesk <no-reply@yourdomain.com>"
ANTHROPIC_API_KEY=<optional, enables the AI assistant>
```

Save the file in nano with Ctrl+O, Enter, then exit with Ctrl+X.

### 6. Start PDFDesk

```bash
docker compose up -d --build
docker compose ps          # all services should be "running"/"healthy"
```

Nginx starts with a temporary self-signed certificate, so the site works over HTTPS straight away, but the browser
will show a warning until the next step.

### 7. Get the free Let's Encrypt certificate

```bash
scripts/init-letsencrypt.sh
```

Open **https://pdf.yourdomain.com**. The `certbot` container renews the certificate automatically, and Nginx reloads
renewed certificates every 6 hours.

### 8. Email (password reset and signature requests)

Use any SMTP provider, such as **Amazon SES**, Gmail with an app password, Zoho or Brevo. With SES, verify your domain,
create SMTP credentials and use `email-smtp.<region>.amazonaws.com` on port `587`.

### 9. USB DSC token signing (optional)

Users who sign with USB tokens run the small bridge program in `tools/dsc-bridge/` on their own PC. See
[tools/dsc-bridge/README.md](tools/dsc-bridge/README.md).

---

## Updating the app

```bash
cd ~/pdfdesk
scripts/update.sh
```

`scripts/update.sh` takes a backup, runs `git pull`, rebuilds the images, restarts the containers with
`docker compose up -d` and removes old images. Database tables are created automatically at startup. If a future
version changes existing tables, its release notes will include the migration command.

---

## Backups

**Create a backup** of the database and all stored files:

```bash
scripts/backup.sh          # writes backups/<date>/pdfdesk.dump and minio-data.tar.gz (keeps the last 14)
```

**Schedule a daily backup** with `crontab -e`:

```
30 2 * * * /home/ubuntu/pdfdesk/scripts/backup.sh >> /home/ubuntu/pdfdesk-backup.log 2>&1
```

**Copy backups off the server**, for example to S3 or Lightsail Object Storage:

```bash
aws s3 sync ~/pdfdesk/backups s3://my-pdfdesk-backups/
```

Lightsail **instance snapshots** (in the Snapshots tab) are also an easy way to capture the whole server.

**Restore** a backup:

```bash
scripts/restore.sh backups/2025-01-31_0230
```

**Database only** (manual):

```bash
docker compose exec -T db pg_dump -U pdfdesk -d pdfdesk --format=custom > pdfdesk.dump
docker compose exec -T db pg_restore -U pdfdesk -d pdfdesk --clean --if-exists < pdfdesk.dump
```

---

## Security notes

* **Passwords** are hashed with bcrypt, and login tokens are JWTs signed with `JWT_SECRET`.
* **Password-reset and signing links** are random tokens. Only their SHA-256 hashes are stored, and they expire or are
  replaced when a reminder is sent.
* **Certificates and passwords** (.pfx/.p12 files, PDF passwords and token PINs) are never stored. Token PINs never
  even reach the server.
* **Uploads** are checked by their real content, limited to 100 MB, and given server-side names.
* **Web page to PDF** blocks private, loopback and metadata IP addresses (SSRF protection), including on redirects and
  sub-requests.
* **Rate limiting** applies per IP in Nginx and in the API, with a stricter limit on login and sign-up.
* **Logs** never contain file contents or secrets.
* **Containers** run as an unprivileged user, and only Nginx is exposed to the internet.
* **Nginx** sets security headers: CSP, HSTS, X-Frame-Options and nosniff.

---

## Running the tests

The tests run without Docker. They use SQLite, local storage and synchronous jobs. Tests that need Ghostscript,
OCRmyPDF or LibreOffice are skipped automatically when those programs are not installed.

```bash
cd backend
pip install -r requirements.txt
pytest
```

Inside the Docker image, where every tool is installed:

```bash
docker compose run --rm api pytest
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Browser shows a certificate warning | Run `scripts/init-letsencrypt.sh` after DNS points to the server, and check that ports 80 and 443 are open in the Lightsail firewall |
| `init-letsencrypt.sh` fails | Check `dig +short pdf.yourdomain.com` shows your static IP, then wait a few minutes after a DNS change |
| Emails do not arrive | Check the `SMTP_*` settings, then run `docker compose logs api` for "Failed to send email" |
| OCR or conversions time out | Use a bigger instance, or raise `OCR_TIMEOUT` / `LIBREOFFICE_TIMEOUT` in `.env`, then run `docker compose up -d` |
| Jobs stay "Waiting in queue" | Run `docker compose ps worker` and `docker compose logs worker`, or raise `WORKER_REPLICAS` |
| AI assistant is missing | Set `ANTHROPIC_API_KEY` in `.env` and run `docker compose up -d` |
| "Too many requests" | Raise `RATE_LIMIT_PER_MINUTE`, or the `rate=` value in `frontend/nginx/*.template` |
| The MinIO image cannot be pulled | Use any S3-compatible storage (AWS S3, Lightsail Object Storage) by setting `S3_ENDPOINT_URL`, `S3_ACCESS_KEY` and `S3_SECRET_KEY` for the backend services in `docker-compose.yml` and removing the `minio` service |
