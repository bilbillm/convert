# 日志与故障排查

日志为逐行 JSON，时间统一使用 UTC。生产日志保存在 `convert_conversion_logs` Docker 卷内，容器路径为 `/logs/`，目录权限 700，文件权限 600，不提交 Git，也没有公开读取接口。容器重建不删除这些日志。当前应用直接运行于阿里云服务器，不依赖工作区隧道。

| 文件 | 覆盖范围 |
| --- | --- |
| `access.jsonl` | 请求方法、路由模板、状态码、耗时、上传/响应字节、响应是否完成 |
| `jobs.jsonl` | 上传、排队、执行、成功/失败、原文件清理、下载、ZIP、过期、重启中断与恢复 |
| `app.jsonl` | 应用启停、转换工具、退出码、超时、缺少组件、异常类型及调用位置 |
| `runtime.jsonl` | 服务 PID、退出和重启、本地健康、剩余磁盘空间 |
| `*-errors.jsonl` | 对应类别的 ERROR/CRITICAL 副本，便于快速查看 |

每个 HTTP 请求生成独立 `request_id`，通过 `X-Request-ID` 响应头返回；上传关联的任务、转换工具事件保留原请求编号，并附带 `job_id`。后续轮询和下载各有自己的请求编号。访问日志使用路由模板，任务操作日志携带任务编号，因此无需记录文件名或完整 URL 即可关联问题。

每类主日志单文件最大 10 MiB，保留当前文件及 5 个历史文件；错误日志单文件 5 MiB，保留当前文件及 3 个历史文件。四类合计约 320 MiB 上限，加上少量单条记录超出。Docker 控制台另保留 5 个 10 MiB 文件，其中包括结构化 Uvicorn 启停/错误记录。历史保留按容量轮转，繁忙时可覆盖较早记录，不承诺固定天数。

不记录文件内容、文件名、请求查询参数、认证头、Cookie、完整转换命令、原始 stderr、异常消息或局部变量。异常保留类型和文件/函数/行号；转换工具 stderr 只记录长度和 SHA-256，便于比较同类故障。隧道原始输出只转换成状态事件。日志中的任务编号依然属于私有运维信息，应仅向管理员开放。

## 查看与关联

```sh
cd /srv/convert
docker exec lumo-convert-server python scripts/logs.py --limit 30
docker exec lumo-convert-server python scripts/logs.py --errors --limit 20
docker exec lumo-convert-server python scripts/logs.py --channel runtime --limit 20
docker exec lumo-convert-server python scripts/logs.py --request-id REQUEST_ID
docker exec lumo-convert-server python scripts/logs.py --job-id JOB_ID
docker exec lumo-convert-server python scripts/logs.py --since 2026-09-30T11:00:00 --errors
docker logs --tail 50 lumo-convert-server
docker inspect --format '{{.State.Status}} {{.State.Health.Status}} {{.RestartCount}}' lumo-convert-server
```

浏览器开发者工具的网络响应头中可找到 `X-Request-ID`。上传响应返回任务编号；`job.failed` 及 `converter.finished` 可定位转换工具、退出码、错误类别和耗时。`upload.disk_full`、`upload.queue_full` 分别表示磁盘保护和队列保护，均不代表固定文件大小限制。

## HTTPS 入口

阿里云 Caddy 仅为该域名新增访问日志，位于 `wmu-campus-wall-portal-edge` 容器 `/data/convert-access.jsonl`，使用原有持久化数据卷。文件权限 600；10 MiB 轮转，最多保留 5 个归档，并清理超过 7 天的归档。过滤请求头、URI、客户端 IP、Set-Cookie 和 Content-Disposition，避免认证信息及文件名进入访问日志。响应头中的 `X-Request-ID` 可与应用记录关联；连接不到应用的 502 不会有应用请求编号。

通过阿里云服务器控制台查看：

```sh
docker exec wmu-campus-wall-portal-edge tail -n 30 /data/convert-access.jsonl
docker logs --since 30m --tail 100 lumo-convert-server
```

旧 Chisel 服务端保留用于回滚，当前业务流量直接由 Caddy 转发到应用容器。Caddy 原有运行错误日志维持已有管理方式，部分运行错误可能包含请求 URI，应视作私有数据，不能公开分享原始日志。其他网站的全局日志配置保持原样。

## 自动恢复与边界

应用退出后由容器监督进程重启，连续三次本地健康失败会终止并重启应用。整个容器退出由 Docker 重启。当前无隧道运行模式下，`health.public` 事件沿用本地探测结果；公网域名需要通过下方显式 HTTPS 检查验证，尚未配置独立的外部监控。

公网健康异常时，本地健康也失败则查应用；本地正常则查 Caddy、私有 Docker 网络和 DNS。运行中任务在进程重启后标记失败并要求重新上传，完成结果在有效期内恢复。

这些日志和监测在当前服务器内运行；整机停止期间不能生成新日志，恢复依赖 Docker 服务和持久化磁盘。当前没有向邮件或聊天发送告警，健康故障会记录到私有错误日志。

```sh
docker exec lumo-convert-server python scripts/test_logging.py
docker exec lumo-convert-server python scripts/check_service.py
python3 scripts/check_service.py --base-url https://convert.lumoren.cn --skip-large
```
