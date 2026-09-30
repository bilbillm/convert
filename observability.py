"""Private, bounded JSON logs; never record filenames, bodies, query strings or credentials."""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

request_id = contextvars.ContextVar('request_id', default=None)
job_id = contextvars.ContextVar('job_id', default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record):
        value = {'time': datetime.now(timezone.utc).isoformat(), 'level': record.levelname,
                 'event': record.getMessage(), 'logger': record.name,
                 'pid': os.getpid(), 'request_id': request_id.get(), 'job_id': job_id.get()}
        value.update(getattr(record, 'fields', {}))
        if record.exc_info:
            kind, _, tb = record.exc_info
            value['exception_type'] = kind.__name__
            # Exception strings, source lines and locals may contain document contents/secrets.
            value['trace'] = [{'file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                              for f in traceback.extract_tb(tb)]
        return json.dumps(value, ensure_ascii=False)


def configure():
    os.umask(0o077)
    root = Path(os.getenv('LOG_DIR', str(Path(__file__).parent / 'logs')))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    formatter = JsonFormatter()
    for channel in ('app', 'access', 'jobs', 'runtime'):
        logger = logging.getLogger('convert.' + channel)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        if logger.handlers:
            continue
        handler = RotatingFileHandler(root / (channel + '.jsonl'), maxBytes=10*1024*1024,
                                      backupCount=5, encoding='utf-8')
        os.chmod(handler.baseFilename, 0o600)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)
        errors = RotatingFileHandler(root / (channel + '-errors.jsonl'), maxBytes=5*1024*1024,
                                     backupCount=3, encoding='utf-8')
        os.chmod(errors.baseFilename, 0o600)
        errors.setLevel(logging.ERROR)
        errors.setFormatter(formatter)
        logger.addHandler(errors)


configure()


def event(channel, name, *, level=logging.INFO, exc_info=False, **fields):
    logging.getLogger('convert.' + channel).log(level, name, extra={'fields': fields}, exc_info=exc_info)


def route_name(scope):
    route = scope.get('route')
    if route:
        return route.path
    return '/' if scope.get('path') == '/' else '<unmatched>'


class RequestLogging:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        rid = uuid.uuid4().hex
        token = request_id.set(rid)
        scope.setdefault('state', {})['request_id'] = rid
        started = time.monotonic()
        status = 500
        received = sent = 0
        completed = False

        async def logged_receive():
            nonlocal received
            message = await receive()
            received += len(message.get('body', b''))
            return message

        async def logged_send(message):
            nonlocal status, sent, completed
            if message['type'] == 'http.response.start':
                status = message['status']
                message['headers'] = list(message.get('headers', [])) + [(b'x-request-id', rid.encode())]
            elif message['type'] == 'http.response.body':
                sent += len(message.get('body', b''))
                completed = not message.get('more_body', False)
            await send(message)

        try:
            await self.app(scope, logged_receive, logged_send)
        except BaseException:
            event('app', 'request.exception', level=logging.ERROR, exc_info=True,
                  route=route_name(scope), method=scope['method'])
            raise
        finally:
            event('access', 'request.finished', level=logging.ERROR if status >= 500 else logging.INFO,
                  route=route_name(scope), method=scope['method'], status=status,
                  duration_ms=round((time.monotonic()-started)*1000, 2),
                  bytes_received=received, bytes_sent=sent, completed=completed)
            request_id.reset(token)
