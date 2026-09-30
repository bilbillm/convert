"""Check streaming accounting, request correlation, privacy and bounded rotation."""
import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
temp = tempfile.TemporaryDirectory()
os.environ['LOG_DIR'] = temp.name
from observability import RequestLogging, JsonFormatter, event, request_id


class LogTests(unittest.TestCase):
    def test_interrupted_job_recovery(self):
        from jobs import install
        class FakeApp:
            routes = {}
            def get(self, path, **kwargs):
                return lambda fn: self.routes.setdefault(path, fn)
            def post(self, path, **kwargs):
                return lambda fn: fn
        with tempfile.TemporaryDirectory() as data:
            os.environ['DATA_DIR'] = data
            root = Path(data)
            for jid, status in [('a'*32, 'running'), ('b'*32, 'done')]:
                folder = root / jid
                folder.mkdir()
                value = {'id': jid, 'status': status, 'created': time.time(),
                         'filename': 'private-document.md', 'target': 'docx'}
                if status == 'done':
                    value['result'] = 'converted.docx'
                    (folder / 'converted.docx').write_bytes(b'completed-result')
                else:
                    (folder / 'source.md').write_bytes(b'private-original')
                (folder / 'job.json').write_text(json.dumps(value))
            app = FakeApp()
            install(app, None, None, None, None)
            status = app.routes['/api/jobs/{job_id}']
            self.assertEqual(status('a'*32)['status'], 'error')
            self.assertFalse((root / ('a'*32) / 'source.md').exists())
            self.assertEqual(status('b'*32)['status'], 'done')
            self.assertTrue((root / ('b'*32) / 'converted.docx').exists())
            lines = (Path(temp.name) / 'jobs.jsonl').read_text()
            self.assertNotIn('private-', lines)
            self.assertIn('job.interrupted', lines)
            os.environ.pop('DATA_DIR')

    def test_stream_and_privacy(self):
        async def app(scope, receive, send):
            scope['route'] = type('Route', (), {'path': '/api/jobs/{job_id}'})()
            self.assertTrue(request_id.get())
            await receive()
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            await send({'type': 'http.response.body', 'body': b'abc', 'more_body': True})
            await send({'type': 'http.response.body', 'body': b'de'})
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': b'secret-document-content'}
        async def send(message):
            messages.append(message)
        scope = {'type': 'http', 'method': 'POST', 'path': '/api/jobs/private-id',
                 'query_string': b'filename=private-name&token=private-token',
                 'headers': [(b'authorization', b'private-auth')]}
        asyncio.run(RequestLogging(app)(scope, receive, send))
        rid = dict(messages[0]['headers'])[b'x-request-id'].decode()
        record = json.loads((Path(temp.name) / 'access.jsonl').read_text().splitlines()[-1])
        self.assertEqual(record['request_id'], rid)
        self.assertEqual(record['bytes_sent'], 5)
        self.assertEqual(record['bytes_received'], 23)
        self.assertTrue(record['completed'])
        self.assertEqual(record['route'], '/api/jobs/{job_id}')
        self.assertNotIn('private-', json.dumps(record))
        self.assertNotIn('secret-document', json.dumps(record))
        self.assertIsNone(request_id.get())

    def test_safe_exception_and_rotation(self):
        logger = logging.getLogger('convert.app')
        file_handler = logger.handlers[0]
        file_handler.maxBytes = 512
        file_handler.backupCount = 2
        try:
            raise ValueError('private-document-content private-token')
        except ValueError:
            event('app', 'test.exception', level=logging.ERROR, exc_info=True)
        record = json.loads((Path(temp.name) / 'app.jsonl').read_text().splitlines()[-1])
        self.assertEqual(record['exception_type'], 'ValueError')
        self.assertTrue(record['trace'])
        self.assertNotIn('private-', json.dumps(record))
        for _ in range(20):
            event('app', 'test.rotation')
        files = list(Path(temp.name).glob('app.jsonl*'))
        self.assertLessEqual(len(files), 3)
        for path in files:
            for line in path.read_text().splitlines():
                json.loads(line)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == '__main__':
    unittest.main()
