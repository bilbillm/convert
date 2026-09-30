# Current deployment status

The application runs in **this managed workspace**, on port 8000. It is not deployed on the Alibaba Cloud server. The public repository is https://github.com/bilbillm/convert.

## Start in this workspace

The required conversion tools and Python dependencies are installed here. A process supervisor can restart the application if its process exits, while this workspace remains active:

```sh
nohup ./scripts/serve.sh > service.log 2>&1 </dev/null &
```

This does not keep the workspace itself alive, restore it after deletion, or create public ingress. Startup after workspace recreation requires the platform's lifecycle configuration.

## Verified

- A streaming upload larger than 25 MB converted successfully.
- Markdown to DOCX/PDF, CSV to XLSX, PNG to WebP, PDF to TXT.
- A broken image failed independently; the other queued jobs completed.
- ZIP output integrity and unsupported-format rejection.
- Actual browser multi-file selection and conversion, desktop and mobile layout.

Repeat the service integration checks with `python scripts/check_service.py` against localhost:8000. The test creates transient conversion jobs and their one-hour results.

## Custom domain dependency

The workspace reports only private network addresses. Runtime status reports no configured ingress capability or outbound identity. The available environment tools do not offer a public port mapping operation. A stable public endpoint accepting inbound HTTPS is still required to serve **convert.lumoren.cn** from this workspace.

Once the platform supplies an endpoint, configure its custom-domain route, add the matching DNS A/CNAME record for `convert`, configure TLS and confirm access externally. Caddy configuration is included for a host with real public inbound ports. DNS has not been changed because there is no verified endpoint to point it at.

Docker Compose configuration validates, but building the optional container encountered Docker Hub's HTTP 429 rate limit. The running workspace service uses installed tools directly, so this does not affect its current local operation.
