"""Container PID 1: supervise app/tunnel, emit bounded logs, probe health, reap children."""
import logging
import os
import signal
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from observability import event

ROOT = Path(__file__).resolve().parent
if ROOT.name == 'scripts':
    ROOT = ROOT.parent
stopping = threading.Event()
children = {}


def stop(signum, frame):
    event('runtime', 'runtime.stopping', signal=signum)
    stopping.set()


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def tunnel_output(pipe):
    for line in iter(pipe.readline, ''):
        # Classify chisel output; never retain raw messages/URLs/authentication.
        line = line.lower()
        state = ('connected' if 'connected (' in line else 'connecting' if 'connecting to' in line
                 else 'retrying' if 'retry' in line else 'error' if 'error' in line
                 else 'disconnected' if 'disconnected' in line else 'message')
        event('runtime', 'tunnel.' + state,
              level=logging.ERROR if state in {'error', 'disconnected'} else logging.INFO)
    pipe.close()


def probe(url, local=False):
    handler = urllib.request.ProxyHandler({}) if local else urllib.request.ProxyHandler()
    with urllib.request.build_opener(handler).open(url, timeout=10) as response:
        return response.status == 200 and b'"ok"' in response.read(4096)


def terminate(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def main():
    event('runtime', 'runtime.started')
    commands = {'app': [str(ROOT / 'run.sh')]}
    if os.getenv('TUNNEL_ENABLED') == '1':
        commands['tunnel'] = [str(ROOT / 'deploy/start-tunnel.sh')]
    retry = dict.fromkeys(commands, 0)
    failures = 0
    next_probe = time.monotonic() + 15
    last_public = None
    while not stopping.is_set():
        now = time.monotonic()
        for name, command in commands.items():
            process = children.get(name)
            if process is not None and process.poll() is not None:
                event('runtime', 'service.exited', level=logging.ERROR, service=name,
                      exit_code=process.returncode, child_pid=process.pid)
                children.pop(name)
                retry[name] = now + 3
            if name not in children and now >= retry[name]:
                try:
                    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                                               stdout=subprocess.PIPE if name == 'tunnel' else None,
                                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
                    children[name] = process
                    event('runtime', 'service.started', service=name, child_pid=process.pid)
                    if name == 'tunnel':
                        threading.Thread(target=tunnel_output, args=(process.stdout,), daemon=True).start()
                except OSError:
                    event('runtime', 'service.start_failed', level=logging.ERROR, exc_info=True, service=name)
                    retry[name] = now + 15
        if now >= next_probe:
            try:
                healthy = probe('http://127.0.0.1:8000/api/health', local=True)
            except Exception:
                healthy = False
            failures = 0 if healthy else failures + 1
            event('runtime', 'health.local', level=logging.INFO if healthy else logging.ERROR,
                  healthy=healthy, consecutive_failures=failures)
            if failures >= 3 and children.get('app'):
                event('runtime', 'health.restart', level=logging.ERROR, service='app')
                terminate(children['app'])
                failures = 0
            try:
                public = probe('https://convert.lumoren.cn/api/health') if 'tunnel' in commands else healthy
            except Exception:
                public = False
            event('runtime', 'health.public', level=logging.INFO if public else logging.ERROR,
                  healthy=public, changed=public != last_public)
            last_public = public
            next_probe = time.monotonic() + 30
        stopping.wait(1)
    for process in list(children.values()):
        terminate(process)
    event('runtime', 'runtime.stopped')


if __name__ == '__main__':
    main()
