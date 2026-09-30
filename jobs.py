"""Disk-backed uploads, isolated conversion jobs, result expiry and ZIP downloads."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask


class ArchiveRequest(BaseModel):
    jobs: list[str] = Field(min_length=1, max_length=500)


def install(app, converter, extension_of, target_formats, safe_stem):
    root = Path(os.getenv('DATA_DIR', str(Path(__file__).parent / 'data'))).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    ttl = int(os.getenv('RESULT_TTL_SECONDS', '3600'))
    workers = ThreadPoolExecutor(max_workers=int(os.getenv('CONVERSION_WORKERS', '2')))
    jobs = {}
    lock = threading.RLock()

    def save(job):
        path = root / job['id'] / 'job.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        temp.replace(path)

    for path in root.glob('*/job.json'):
        try:
            job = json.loads(path.read_text())
            if job['status'] == 'done' and time.time() - job['created'] < ttl:
                jobs[job['id']] = job
            else:
                shutil.rmtree(path.parent, ignore_errors=True)
        except (OSError, ValueError, KeyError):
            shutil.rmtree(path.parent, ignore_errors=True)
    for folder in root.iterdir():
        if folder.is_dir() and not (folder / 'job.json').exists():
            shutil.rmtree(folder, ignore_errors=True)

    def process(job, source, folder):
        with lock:
            job['status'] = 'running'
            save(job)
        try:
            output = converter(source, job['target'], folder)
            if not output.is_file() or not output.stat().st_size:
                raise ValueError('转换没有生成有效文件。')
            with lock:
                job.update(status='done', result=str(output.relative_to(folder)), size=output.stat().st_size)
        except Exception as exc:
            with lock:
                job.update(status='error', error=getattr(exc, 'message', '无法转换此文件，请检查文件和输出格式。'))
        finally:
            # Originals, converter profiles and intermediate files are not retained.
            keep = (folder / job['result']).resolve() if job.get('result') else None
            for child in sorted(folder.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if child.is_file() and child.resolve() != keep and child.name != 'job.json':
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
            with lock:
                job['finished'] = time.time()
                save(job)

    def lookup(job_id):
        with lock:
            job = jobs.get(job_id)
            if not job or (job['status'] in {'done', 'error'} and time.time() - job.get('finished', job['created']) > ttl):
                raise HTTPException(404, '任务不存在或已经过期。')
            return dict(job)

    def sweep():
        while True:
            time.sleep(60)
            with lock:
                expired = [key for key, value in jobs.items() if value['status'] in {'done', 'error'} and time.time() - value.get('finished', value['created']) > ttl]
                for key in expired:
                    jobs.pop(key, None)
                    shutil.rmtree(root / key, ignore_errors=True)
    threading.Thread(target=sweep, daemon=True).start()

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'upload_size_limit': None, 'workers': int(os.getenv('CONVERSION_WORKERS', '2'))}

    @app.post('/api/jobs', status_code=202)
    async def upload(request: Request, filename: str, target: str):
        extension = extension_of(filename)
        if target not in target_formats(extension):
            raise HTTPException(400, '文件类型或输出格式不受支持。')
        with lock:
            if sum(j['status'] in {'uploading', 'queued', 'running'} for j in jobs.values()) >= 100:
                raise HTTPException(429, '队列暂时已满，请稍后重试。')
            job_id = uuid.uuid4().hex
            folder = root / job_id
            folder.mkdir(mode=0o700)
            job = dict(id=job_id, filename=filename[:255], target=target, status='uploading', created=time.time())
            jobs[job_id] = job
        source = folder / ('source.' + extension)
        total = 0
        try:
            with source.open('wb') as stream:
                async for chunk in request.stream():
                    if shutil.disk_usage(root).free < max(len(chunk) * 2, 128 * 1024 * 1024):
                        raise HTTPException(507, '服务器可用磁盘空间不足，请稍后重试。')
                    await asyncio.to_thread(stream.write, chunk)
                    total += len(chunk)
            if not total:
                raise HTTPException(400, '文件内容为空。')
            with lock:
                job['status'] = 'queued'
                save(job)
            workers.submit(process, job, source, folder)
            return {'id': job_id, 'status': 'queued'}
        except BaseException:
            with lock:
                jobs.pop(job_id, None)
            shutil.rmtree(folder, ignore_errors=True)
            raise

    @app.get('/api/jobs/{job_id}')
    def status(job_id: str):
        job = lookup(job_id)
        job.pop('result', None)
        if job['status'] == 'done':
            job['download'] = f'/api/jobs/{job_id}/download'
        return job

    @app.get('/api/jobs/{job_id}/download')
    def download(job_id: str):
        job = lookup(job_id)
        if job['status'] != 'done':
            raise HTTPException(409, '任务尚未完成。')
        return FileResponse(root / job_id / job['result'], filename=f"{safe_stem(job['filename'])}.{job['target']}")

    @app.post('/api/archive')
    def archive(body: ArchiveRequest):
        selected = [lookup(key) for key in dict.fromkeys(body.jobs)]
        if any(job['status'] != 'done' for job in selected):
            raise HTTPException(409, '请只打包已完成的任务。')
        fd, name = tempfile.mkstemp(prefix='lumo-results-', suffix='.zip', dir=root)
        os.close(fd)
        path = Path(name)
        try:
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
                for index, job in enumerate(selected, 1):
                    archive.write(root / job['id'] / job['result'], f"{index:03d}-{safe_stem(job['filename'])}.{job['target']}")
            return FileResponse(path, filename='Lumo-Convert.zip', background=BackgroundTask(path.unlink, missing_ok=True))
        except Exception:
            path.unlink(missing_ok=True)
            raise
