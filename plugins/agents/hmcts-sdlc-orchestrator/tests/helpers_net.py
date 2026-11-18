"""Loopback helpers shared by the receiver and lifecycle tests (no proxies, sockets always closed)."""
import gzip
import http.client
import json
import socket
from typing import Optional, Tuple


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def free_port_run(span: int = 10) -> int:
    """A base port with ``span`` consecutive free ports, all inside 1024-65535."""
    for _ in range(100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            base = sock.getsockname()[1]
        if 1024 <= base and base + span <= 65535 and all(port_is_free(p) for p in range(base, base + span)):
            return base
    raise RuntimeError("no free port run found")


def request(port: int, method: str, path: str, body: Optional[bytes] = None, headers: Optional[dict] = None,
            timeout: float = 5.0) -> Tuple[int, object]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        raw = resp.read()
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            data = raw
        return resp.status, data
    finally:
        conn.close()


def post_json(port: int, path: str, payload, gzipped: bool = False) -> Tuple[int, object]:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if gzipped:
        body = gzip.compress(body)
        headers["Content-Encoding"] = "gzip"
    return request(port, "POST", path, body=body, headers=headers)
