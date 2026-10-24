# Lumo Convert

A Chinese document and image converter with a Swiss International Style interface, batch queues, individual downloads and ZIP downloads. Website: **https://convert.lumoren.cn/**. Runtime target: the Alibaba Cloud server behind the public domain.

## Uploads and privacy

There is no application-level file size cap. Uploads stream to disk instead of being loaded entirely into memory. Actual capacity depends on available disk, upstream limits, and converter resources. Uploads stop with a clear error when storage is nearly exhausted. Conversion workers run independently; one failed file does not stop a batch. Results expire after one hour. Uploaded originals are removed after processing. The production domain requires the unified Authelia login. A signed-in authorized user holding a job URL can download it until expiry; the application itself does not implement separate user-owned task storage.

## Run

Python 3.12+, LibreOffice, Pandoc, ImageMagick, and Poppler are required. Install Chinese fonts for document rendering.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PATH="$PWD/.venv/bin:$PATH" ./run.sh
```

The service listens on port 8000. Configure `DATA_DIR`, `CONVERSION_WORKERS` (default 2), `CONVERSION_TIMEOUT_SECONDS` (default 600), and `RESULT_TTL_SECONDS` (default 3600). Use one Uvicorn process because the queue is in-process. Restarting marks interrupted jobs as failed with a retry message; successfully completed results remain until expiry.

## Format support

- Documents: DOC, DOCX, DOCM, ODT, RTF, TXT, Markdown, HTML, EPUB, FB2, LaTeX, RST, Org and GFM.
- Sheets: XLS, XLSX, XLSM, ODS, CSV, TSV.
- Presentations: PPT, PPTX, PPTM, ODP.
- PDF: text extraction and first-page image rendering.
- Images: PNG, JPEG, WebP, GIF, TIFF, BMP, ICO, JPEG 2000, DDS, PSD, PCX, TGA, PPM and other installed ImageMagick formats. AVIF/HEIC support depends on installed delegates.

The output list is filtered by input family. AsciiDoc is output-only because Pandoc has no AsciiDoc reader. Office/PDF to images exports the first page; most image outputs use the first frame. Office layout may change between formats. SVG is intentionally excluded because it can refer to external resources. Conversion processes use time and memory controls; removing upload caps does not provide unlimited resources.

## Public deployment

`compose.yaml` exposes the app at localhost:8000 and persists jobs in a Docker volume. `compose.public.yaml` adds Caddy for HTTPS when the host has working public ingress on ports 80/443. Existing reverse proxies can forward to localhost:8000 instead; disable their upload body size limit if desired.

```sh
docker compose up --build -d
# Only after public ingress and DNS exist:
docker compose -f compose.yaml -f compose.public.yaml up --build -d
```

The active deployment runs the application directly on the Alibaba Cloud server, on the private Docker network shared with its existing Caddy ingress. It no longer depends on a reverse tunnel or a separate workspace. DNS and HTTPS stay on `convert.lumoren.cn`.

```sh
# On the ingress server, with the existing lumo_convert_relay network:
docker compose -f compose.yaml -f compose.server.yaml up --build -d
```

Install the site block from `deploy/server.Caddyfile` in the existing Caddy configuration, validate and reload it. Preserve other domains. The server override uses one conversion worker, a 768 MB memory ceiling, a 512 MB temporary filesystem and bounded Docker logs. Application data and private logs persist in Docker volumes; completed results expire after one hour.

See [DEPLOYMENT.md](DEPLOYMENT.md) for deployment, verification and rollback. The old `compose.workspace.yaml` and `deploy/relay.Caddyfile` remain available for the historical workspace/tunnel deployment. See [LOGGING.md](LOGGING.md) for private structured logs.

## Unified login (2026-10-24)

The production domain now uses the Caddy `private_auth` wrapper around the existing `admin_auth` snippet and Authelia's `lumo-private` rule. The `lumoren` account is authorized; existing campus-wall operators keep their original access and are not automatically granted private tools. Session cookies cover `lumoren.cn`; public display sites and Study keep their existing access behavior. Credentials stay in the private Authelia file backend and are never committed here.

Unauthenticated API requests receive 401; browser navigation redirects to the existing unified login portal. Uploads, task queries, results and ZIP downloads all pass the same gate. The interface handles expired sessions and provides a unified logout link. The internal container health probe remains local and requires no cookie.

Run the local service check inside the container as before. For HTTPS verification, sign in first and supply a temporary authenticated Cookie header through an environment variable:

```sh
python3 scripts/check_service.py --base-url https://convert.lumoren.cn --skip-large --cookie-env CONVERT_SESSION_COOKIE
```

Do not place the cookie value in command arguments, committed files or logs. The shared gateway's active configuration and private Authelia backup are recorded in `/srv/lumoren-access/`.
