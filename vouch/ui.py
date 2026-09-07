"""Serve the dashboard locally.

There is one page, in docs/. The hosted copy and this one are the same files,
so they cannot drift apart: the only difference is that here the snapshot is
generated live from your own memory store rather than read from a file
committed at build time.

    python -m vouch ui        then open http://127.0.0.1:8765

The page verifies everything in the browser regardless of who serves it, so
this process is a static file server plus one generated document. It holds no
key and signs nothing.
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

DOCS = Path(__file__).resolve().parent.parent / "docs"
DB = os.environ.get("VOUCH_DB", ".vouch/memory.db")

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


def build_snapshot(network: str) -> dict:
    """The same document scripts/export_snapshot.py writes, made on demand."""
    from .chain import Chain
    from .memory import VouchMemory
    from .publish import EvidenceStore
    from .trust import TrustEngine

    suffix = network.replace("-", "_").upper()
    subject = int(os.environ.get(f"VOUCH_SUBJECT_AGENT_ID_{suffix}", "0") or 0)

    if not Path(DB).exists():
        return {"error": "no memory yet — run `python -m vouch seed` first"}

    mem = VouchMemory(DB)
    chain = Chain(network)

    hints = []
    for r in chain.ratings(subject, memory=mem):
        if r.get("block"):
            hints.append({"client": r["client"], "index": r["index"],
                          "block": r["block"], "uri": r["feedback_uri"]})

    engine = TrustEngine(mem)
    from datetime import datetime, timezone

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network": {
            "name": network, "chain_id": chain.cfg["chain_id"],
            "rpc": chain.cfg["rpc"],
            "rpcs": [chain.cfg["rpc"],
                     "https://base-sepolia-rpc.publicnode.com",
                     "https://base-sepolia.drpc.org"],
            "explorer": chain.cfg["explorer"],
            "reputation": chain.cfg["reputation"], "identity": chain.cfg["identity"],
        },
        "issuer": {
            "handle": os.environ.get("VOUCH_HANDLE", "attrito.vouch"),
            "address": os.environ.get("VOUCH_ADDRESS", ""),
            "agent_id": int(os.environ.get(f"VOUCH_AGENT_ID_{suffix}", "0") or 0),
        },
        "subject_agent_id": subject,
        "memory": {
            "schema_version": mem.schema_version(),
            "counterparties": [
                {
                    "handle": c.get("handle"), "agent_id": c.get("agent_id"),
                    "jobs_completed": c.get("jobs_completed", 0),
                    "jobs_disputed": c.get("jobs_disputed", 0),
                    "flagged": bool(mem.is_flagged(c.get("handle", ""))),
                }
                for c in mem.list_counterparties()
            ],
            "policy": mem.get_policy(),
            "incidents": [
                {
                    "ts": e.get("ts") or e.get("created_at"),
                    "handle": (e.get("extra") or {}).get("handle"),
                    "kind": (e.get("extra") or {}).get("kind"),
                    "detail": (e.get("acted") or [""])[0],
                }
                for h in {c.get("handle") for c in mem.list_counterparties() if c.get("handle")}
                for e in mem.incidents(h)
            ],
        },
        "offline_verdicts": {
            "newcomer": engine.decide("newcomer", standard_price_usd=25.0).to_dict(),
            "swiftrender": engine.decide("swiftrender", standard_price_usd=25.0).to_dict(),
        },
        "log_hints": hints,
        "evidence_base_url": os.environ.get("VOUCH_EVIDENCE_BASE_URL", ""),
        "evidence_files": EvidenceStore().list(),
    }


class Handler(BaseHTTPRequestHandler):
    network = "base-sepolia"
    read_only = False

    def log_message(self, *a):  # keep the terminal clean while filming
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                self._file("index.html")
            elif path == "/snapshot.json":
                snap = build_snapshot(self.network)
                self._send(200, json.dumps(snap, default=str).encode(), TYPES[".json"])
            else:
                self._file(path.lstrip("/"))
        except FileNotFoundError:
            self._send(404, b'{"error":"not found"}', TYPES[".json"])
        except Exception as exc:
            self._send(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode(), TYPES[".json"])

    def _file(self, name: str) -> None:
        # Resolve inside docs/ only: a served path must never escape the
        # directory, however it is spelled.
        target = (DOCS / name).resolve()
        if not str(target).startswith(str(DOCS.resolve())) or not target.is_file():
            raise FileNotFoundError(name)
        self._send(200, target.read_bytes(), TYPES.get(target.suffix, "application/octet-stream"))


from .config import apply_public_defaults  # noqa: E402


def serve(
    port: int = 8765,
    network: str = "base-sepolia",
    open_browser: bool = True,
    host: str = "127.0.0.1",
    read_only: bool = False,
) -> int:
    apply_public_defaults()
    Handler.network = network
    Handler.read_only = read_only

    if read_only:
        leaked = [
            k for k in ("VOUCH_PRIVATE_KEY", "VOUCH_COUNTERPARTY_KEY",
                        "VOUCH_SECOND_ISSUER_KEY", "SELLER_SIGNER_PRIVATE_KEY")
            if os.environ.get(k)
        ]
        if leaked:
            print(f"  refusing to start read-only with keys present: {', '.join(leaked)}")
            return 2

    httpd = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    print(f"  Vouch case file on http://{shown}:{port}   (network: {network})")
    print("  ctrl-c to stop")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(f"http://{shown}:{port}")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()
    return 0
