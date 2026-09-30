"""Run Uvicorn without its raw access log or sensitive exception messages."""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn
from observability import JsonFormatter


class ServerFormatter(JsonFormatter):
    def format(self, record):
        record.msg = 'server.' + record.levelname.lower()
        record.args = ()
        return super().format(record)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ServerFormatter())
for name in ('uvicorn', 'uvicorn.error'):
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

uvicorn.run('main:app', host=os.getenv('HOST', '0.0.0.0'), port=int(os.getenv('PORT', '8000')),
            workers=1, access_log=False, log_config=None, proxy_headers=False)
