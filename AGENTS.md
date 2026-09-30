# Project instructions

Lumo Convert runs in the current managed workspace. The public domain is convert.lumoren.cn. Alibaba Cloud Caddy provides HTTPS and relays traffic through an authenticated reverse tunnel; conversion and job storage stay in this workspace.

- Keep the interface Chinese, accessible, responsive, and visually restrained.
- Do not configure an application upload size cap. Stream uploads to disk.
- Batch jobs must fail independently and expose their individual status.
- Run converters with argument arrays, never with a shell. Use unique work directories.
- Keep uploaded files, generated output, authentication and environment credentials out of Git.
- Retain results for one hour, then remove their work directories.
- Use clear, focused commits for docs, backend, batch jobs, interface, and deployment.
- Inspect existing services and public ingress before deploying. Do not change other hosts.
- Verify real conversions when changing conversion logic and record known format limitations.
- A listening local service is not evidence that the custom domain is deployed.

- Keep .secrets/ and .local/ excluded from Git. Never publish tunnel credentials or private keys.
- Verify public ingress after changes using the small-fixture service check.

- Run production app/tunnel with the workspace Compose override, never tool-session processes.
- Use structured events and correlation IDs; never log upload contents, filenames, raw URLs/query strings, headers, credentials or raw converter stderr.
- Keep logs private, rotated and excluded from Git/build context; no public log download endpoint.
- Verify public health, real conversions, log privacy and automatic recovery after runtime changes.
