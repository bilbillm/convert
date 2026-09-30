"""Exercise real conversions against a running server; no credentials required."""
import argparse
import base64
import io
import json
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--base-url', default='http://127.0.0.1:8000')
parser.add_argument('--skip-large', action='store_true')
args = parser.parse_args()
BASE = args.base_url.rstrip('/')


def request(path, data=None, content_type=None):
    headers = {'Content-Type': content_type} if content_type else {}
    return urllib.request.urlopen(urllib.request.Request(BASE + path, data=data, headers=headers), timeout=60)


def submit(name, target, data):
    query = urllib.parse.urlencode({'filename': name, 'target': target})
    return json.load(request('/api/jobs?' + query, data, 'application/octet-stream'))['id']


def wait(job):
    deadline = time.time() + 180
    while time.time() < deadline:
        result = json.load(request('/api/jobs/' + job))
        if result['status'] in ('done', 'error'):
            return result
        time.sleep(.3)
    raise AssertionError('Conversion did not finish')


png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
with tempfile.TemporaryFile() as large:
    large.write(png)
    if not args.skip_large:
        large.write(b'\0' * (26 * 1024 * 1024))
    large.seek(0)
    # urllib streams a file-like request rather than retaining the upload in RAM.
    large_job = submit('image.png' if args.skip_large else 'over-25mb.png', 'webp', large)

cases = [('notes.md', 'docx', b'# Hello\n\nConversion example.'), ('notes.md', 'pdf', b'# Hello\n\nConversion example.'), ('table.csv', 'xlsx', b'name,value\nfirst,42\n'), ('broken.png', 'jpg', b'invalid image')]
job_ids = [submit(*case) for case in cases]
results = [wait(job) for job in [large_job] + job_ids]
for result in results:
    print(result['filename'], result['status'], result.get('error', ''))
assert all(result['status'] == 'done' for result in results[:-1]), results
assert results[-1]['status'] == 'error', results
pdf_id = job_ids[1]
pdf = request('/api/jobs/' + pdf_id + '/download').read()
assert pdf.startswith(b'%PDF')
text_id = submit('output.pdf', 'txt', pdf)
assert wait(text_id)['status'] == 'done'
assert b'Hello' in request('/api/jobs/' + text_id + '/download').read()
ids = [result['id'] for result in results if result['status'] == 'done']
archive = request('/api/archive', json.dumps({'jobs': ids}).encode(), 'application/json').read()
with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
    assert len(zip_file.namelist()) == len(ids)
    assert zip_file.testzip() is None
assert json.load(request('/api/health'))['upload_size_limit'] is None
try:
    submit('../unknown.exe', 'png', b'bad')
except urllib.error.HTTPError as exc:
    assert exc.code == 400
else:
    raise AssertionError('Unsupported file accepted')
print('PASS: streaming upload, document/PDF/image/sheet conversions, isolated failure, ZIP and type validation; large upload:', not args.skip_large)
