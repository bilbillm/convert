# Deployment

Protected URL: **https://convert.lumoren.cn/**

Source: https://github.com/bilbillm/convert

## Direct server deployment (2026-10-24)

The application now runs on the Alibaba Cloud ingress server itself, from `/srv/convert`. Previously Caddy forwarded to a reverse tunnel into a separate workspace. That application was unavailable and the public domain returned HTTP 502. The direct deployment removes that workspace dependency.

Traffic flows from HTTPS Caddy (`wmu-campus-wall-portal-edge`) to `lumo-convert-server:8000` on the existing private Docker network `lumo_convert_relay`. DNS and TLS are unchanged. Only the `convert.lumoren.cn` site block changes; other domains retain their configuration. The old tunnel container and credentials are retained for rollback, but application traffic no longer uses them.

The server runs Docker Compose with the existing PID 1 supervisor:

```sh
cd /srv/convert
docker compose -f compose.yaml -f compose.server.yaml up --build -d
```

The override uses one conversion worker, a 768 MB memory limit, one CPU and a 512 MB temporary filesystem to fit the server alongside its existing services. Large or complex files may exceed these resources. There is no application upload size cap. The root filesystem is read-only, privileges are dropped and the service has no published host application port. The application shares the private relay network with Caddy.

Named volumes `convert_conversion_data` and `convert_conversion_logs` persist jobs and private rotated logs across container recreation. Do not use `down --volumes` during updates. Original uploads are deleted after processing; results expire after one hour. No previous workspace data was copied to this server.

## HTTPS ingress

The active Caddy configuration is mounted from:

```text
/home/admin/wmu-campus-wall/.runtime/production-sites/Caddyfile
```

Use the site block in `deploy/server.Caddyfile`. Before changing the active file, preserve a backup in `/opt/lumo-convert-relay/`; edit the file in place so the existing bind mount sees the update. Validate before reloading:

```sh
docker exec wmu-campus-wall-portal-edge caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec wmu-campus-wall-portal-edge caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

Caddy must remain on `lumo_convert_relay`. If its original Compose project recreates it without this network, reconnect it with `docker network connect lumo_convert_relay wmu-campus-wall-portal-edge` before reloading. Do not modify DNS to recover an application container.

## Build with the host's existing proxy

The server has an existing loopback HTTP proxy. If a standard Compose build cannot download dependencies promptly, build using that proxy, then run Compose without `--build`:

```sh
docker build --network host \
  --build-arg HTTP_PROXY --build-arg HTTPS_PROXY --build-arg ALL_PROXY \
  --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t lumo-convert:local .
docker compose -f compose.yaml -f compose.server.yaml up -d
```

These special Docker proxy arguments are used at build time; no proxy credentials or tunnel keys are placed in the source or image. Runtime conversion remains on private Docker networks. Do not change the system proxy or other services to build this application.

## Verification

```sh
curl --fail https://convert.lumoren.cn/api/health
python3 scripts/check_service.py --base-url https://convert.lumoren.cn --skip-large
docker exec lumo-convert-server python scripts/check_service.py
```

The service check creates small temporary jobs, exercises actual document/PDF/image/spreadsheet conversion, verifies independent invalid-file failure and tests ZIP integrity and type validation. The local default additionally uploads more than 25 MB. Completed results expire normally.

Private log checks run inside the image without host Python dependencies:

```sh
docker exec lumo-convert-server python scripts/test_logging.py
```

Inspect only filtered operational events when troubleshooting; never publish uploads, task metadata, keys or raw logs. See `LOGGING.md` for event names and privacy rules. In the server deployment, logs live in the named Docker volume rather than a checkout `logs/` directory.

## Verified on 2026-10-24

- Public HTTPS health and HTTP-to-HTTPS redirect after migration.
- Actual Markdown to DOCX/PDF, CSV to XLSX, PNG to WebP and PDF to text through the public domain; valid ZIP and independent invalid-image failure.
- Local streaming upload larger than 25 MB.
- Browser layouts at 1440, 768, 390 and 320 pixels without horizontal overflow; native file selection, mixed batch, individual download, ZIP and no script errors.
- Staggered CSS entrances, hover/focus feedback, file-row entrances and drag feedback; reduced-motion mode disables animations, transitions and smooth scrolling.
- Three existing privacy, log rotation and interrupted-job recovery tests.
- Application child termination followed by supervisor recovery; simulated supervisor crash followed by Docker restart; completed result remained downloadable through HTTPS after both.
- Blog, campus portal, study and dashboard endpoints remained HTTP 200 after the ingress update.

The ingress backup for this migration is `/opt/lumo-convert-relay/Caddyfile.before-direct-20261024`. Browser QA installed supporting graphics libraries on the host; it did not upgrade existing packages.

## Recovery and rollback

Compose sets `restart: unless-stopped`; PID 1 independently supervises the application and restarts it after a child exit or three failed local health probes. Both host restarts and container recreation preserve named volumes. A deliberate `docker stop` suppresses automatic restart until explicitly started again.

For an interface-only rollback, restore `static/index.html` from the desired Git revision, rebuild the image and run the same Compose command. Preserve the data and log volumes.

For an ingress rollback, restore the pre-migration Caddy backup in place, validate and reload it. The old tunnel deployment will only serve successfully if its separate workspace and tunnel client are restored. The historical files `compose.workspace.yaml` and `deploy/relay.Caddyfile` document that topology; they are not the active server configuration.

## Unified login (2026-10-24)

The production domain now uses the Caddy `private_auth` wrapper around the existing `admin_auth` snippet and Authelia's `lumo-private` rule. The `lumoren` account is authorized; existing campus-wall operators keep their original access and are not automatically granted private tools. Session cookies cover `lumoren.cn`; public display sites and Study keep their existing access behavior. Credentials stay in the private Authelia file backend and are never committed here.

Unauthenticated API requests receive 401; browser navigation redirects to the existing unified login portal. Uploads, task queries, results and ZIP downloads all pass the same gate. The interface handles expired sessions and provides a unified logout link. The internal container health probe remains local and requires no cookie.

Run the local service check inside the container as before. For HTTPS verification, sign in first and supply a temporary authenticated Cookie header through an environment variable:

```sh
python3 scripts/check_service.py --base-url https://convert.lumoren.cn --skip-large --cookie-env CONVERT_SESSION_COOKIE
```

Do not place the cookie value in command arguments, committed files or logs. The shared gateway's active configuration and private Authelia backup are recorded in `/srv/lumoren-access/`.
