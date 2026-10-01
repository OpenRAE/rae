"""Synthetic effect service in a process independent of candidate workers."""

from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import multiprocessing
import os
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request


def _serve(connection):
    state = defaultdict(
        lambda: {"requests": 0, "effects": 0, "events": [], "caller_pids": []}
    )
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, value):
            data = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            key = urllib.parse.unquote(self.path[1:])
            with lock:
                result = json.loads(json.dumps(state[key]))
            self.reply(result)

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            key = data["key"]
            with lock:
                state[key]["requests"] += 1
                state[key]["caller_pids"].append(data["caller_pid"])
                state[key]["events"].append(["request", time.monotonic()])
            time.sleep(data.get("delay", 0))
            with lock:
                state[key]["effects"] += 1
                state[key]["events"].append(["effect", time.monotonic()])
            time.sleep(data.get("ack_delay", 0))
            self.reply({"applied": True})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    connection.send(f"http://127.0.0.1:{server.server_port}")
    connection.close()
    server.serve_forever()


class Witness:
    def __enter__(self):
        parent, child = multiprocessing.Pipe()
        self.process = multiprocessing.Process(
            target=_serve, args=(child,), daemon=True
        )
        self.process.start()
        if not parent.poll(5):
            self.process.terminate()
            self.process.join(5)
            raise TimeoutError("witness startup")
        self.url = parent.recv()
        parent.close()
        child.close()
        return self

    def __exit__(self, *_args):
        self.process.terminate()
        self.process.join(5)


def effect(url, key, delay=0, ack_delay=0, timeout=10):
    data = json.dumps(
        {"key": key, "delay": delay, "ack_delay": ack_delay, "caller_pid": os.getpid()}
    ).encode()
    req = urllib.request.Request(
        url + "/effect", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def observe(url, key):
    with urllib.request.urlopen(
        url + "/" + urllib.parse.quote(key), timeout=3
    ) as response:
        return json.load(response)


def wait_for(url, key, field="requests", count=1, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = observe(url, key)
        if state[field] >= count:
            return state
        time.sleep(0.01)
    raise TimeoutError(f"witness {key} {field}<{count}")


def record(name, value):
    Path("results").mkdir(exist_ok=True)
    Path("results", name + ".json").write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps({"probe": name, **value}), flush=True)
