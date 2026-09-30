# Deployment

Public URL: **https://convert.lumoren.cn/**
Source: https://github.com/bilbillm/convert

## Where the application runs

Conversion workers and job storage run in this managed workspace at port 8000. Alibaba Cloud is the public HTTPS ingress and tunnel endpoint; it does not process uploaded documents or images.

```mermaid
flowchart LR
    Browser[Browser] -->|HTTPS| Edge[Alibaba Cloud Caddy]
    Edge -->|Internal Docker network| Tunnel[Authenticated tunnel server]
    Tunnel -->|Encrypted reverse tunnel| Workspace[Current workspace :8000]
```

## DNS and TLS

Alibaba Cloud DNS has an enabled A record: host `convert`, value `47.116.190.234`, TTL 600 seconds. The existing Caddy ingress redirects HTTP to HTTPS and issues/renews the certificate. The additional site configuration is in `deploy/relay.Caddyfile`.

The existing Caddy container is `wmu-campus-wall-portal-edge`. It now also joins a dedicated internal Docker network, `lumo_convert_relay`. Container `lumo-convert-tunnel` listens on ports 19001 and 18000 inside that network. Neither tunnel port is published on the host. The relay has a restart policy, 128 MB memory limit and restricted forwarding credentials. Caddy's earlier configuration is backed up at `/opt/lumo-convert-relay/Caddyfile.before-convert`.

## Workspace processes

Keep two processes running in persistent execution sessions:

```sh
./scripts/serve.sh
./deploy/start-tunnel.sh
```

The first supervises the app. The second uses Chisel 1.12.0 and reconnects automatically through the inherited HTTPS proxy, with TLS verification and a pinned server public-key fingerprint. Its reverse target is `R:0.0.0.0:18000:127.0.0.1:8000` inside the relay container. The domain only reaches the app while this workspace and its tunnel remain active. Workspace recreation requires restoring dependencies, private tunnel credentials, job storage, and its startup sessions.

The tunnel executable is `.local/bin/chisel`; it was checked against the publisher's SHA-256 checksum. Credentials and the fingerprint are stored in `.secrets/`, with private file permissions, and are excluded from Git. The server has separately protected authentication and key files. Deployment credentials are never included in the public repository.

## Verified

- Local streaming upload larger than 25 MB.
- Actual Markdown to DOCX/PDF, CSV to XLSX, PNG to WebP, PDF to TXT.
- Broken image failure independent of the other jobs.
- ZIP integrity and unsupported file rejection.
- Browser multi-file selection/conversion, desktop and mobile layout.
- DNS resolution, HTTPS health response, and HTTP-to-HTTPS redirect through the public domain.
- Real document/image/sheet conversions and ZIP downloads through the public HTTPS URL.
- Existing blog and portal health checks after the Caddy addition.

Check the running service locally:

```sh
python scripts/check_service.py
```

Check small fixtures through the public domain:

```sh
python scripts/check_service.py --base-url https://convert.lumoren.cn --skip-large
```

These checks create temporary jobs and one-hour results. The optional application Docker configuration validates, but its image build was interrupted by Docker Hub's HTTP 429 rate limit. The active workspace app uses installed conversion components directly.

## Recovery

After a workspace interruption, restore `.secrets/` privately and start the two workspace processes. Check `/api/health` through the public hostname. If the existing Caddy container is recreated by its original Compose project, reconnect it to the dedicated network with `docker network connect lumo_convert_relay wmu-campus-wall-portal-edge`. Normal container/host restarts preserve the connection. Do not change the DNS A record when restarting the workspace: the ingress address remains the same.

To roll back only the Caddy addition, restore the backup into the mounted config file in place, validate and reload Caddy. The relay container and its dedicated network can then be removed after disconnecting Caddy. Preserve the existing site's other networks, volumes and configuration.
