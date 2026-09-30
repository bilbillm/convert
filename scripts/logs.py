"""Local-only JSON log search. Example: python scripts/logs.py --errors --limit 20."""
import argparse
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--dir', default=os.getenv('LOG_DIR', str(Path(__file__).resolve().parent.parent / 'logs')))
parser.add_argument('--channel', choices=['access', 'app', 'jobs', 'runtime'])
parser.add_argument('--request-id')
parser.add_argument('--job-id')
parser.add_argument('--errors', action='store_true')
parser.add_argument('--since', help='UTC ISO timestamp, e.g. 2026-09-30T12:00:00')
parser.add_argument('--limit', type=int, default=50)
args = parser.parse_args()
channels = [args.channel] if args.channel else ['access', 'app', 'jobs', 'runtime']
matches = []
for channel in channels:
    for path in Path(args.dir).glob(channel + '.jsonl*'):
        with path.open() as stream:
            for line in stream:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if args.request_id and item.get('request_id') != args.request_id:
                    continue
                if args.job_id and item.get('job_id') != args.job_id:
                    continue
                if args.errors and item.get('level') not in {'ERROR', 'CRITICAL'}:
                    continue
                if args.since and item.get('time', '') < args.since:
                    continue
                matches.append(item)
                if len(matches) > max(args.limit * 2, 100):
                    matches = sorted(matches, key=lambda x: x['time'])[-max(args.limit, 1):]
for item in sorted(matches, key=lambda x: x['time'])[-max(args.limit, 1):]:
    print(json.dumps(item, ensure_ascii=False))
