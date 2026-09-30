# Lumo Convert

A Chinese document and image converter with an Apple-inspired interface, batch queues, individual downloads and ZIP downloads. Intended hostname: **convert.lumoren.cn**. Runtime target: this managed workspace.

## Uploads and privacy

There is no application-level file size cap. Uploads stream to disk instead of being loaded entirely into memory. Actual capacity depends on available disk, upstream limits, and converter resources. Uploads stop with a clear error when storage is nearly exhausted. Conversion workers run independently; one failed file does not stop a batch. Results expire after one hour. Uploaded originals are removed after processing. Anyone who has a job's unguessable URL can download it until expiry; no user accounts are provided.

## Run

Python 3.12+, LibreOffice, Pandoc, ImageMagick, and Poppler are required. Install Chinese fonts for document rendering.

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PATH="$PWD/.venv/bin:$PATH" ./run.sh
```

The service listens on port 8000. Configure `DATA_DIR`, `CONVERSION_WORKERS` (default 2), `CONVERSION_TIMEOUT_SECONDS` (default 600), and `RESULT_TTL_SECONDS` (default 3600). Use one Uvicorn process because the queue is in-process. Restarting removes interrupted jobs; successfully completed results remain until expiry.

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

Point DNS host `convert` to a verified stable public IP (A record), or to a supported hostname (CNAME). This workspace currently exposes private addresses; no stable public ingress has been confirmed. Do not point the domain to an unrelated host or claim production is live without checking it externally. Keeping this workspace running and retaining its disk is required for availability.
