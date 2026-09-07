"""A local dashboard for Vouch.

Standard library only: no framework, no build step, no extra dependency. It
serves one page and a few JSON endpoints backed by the same code the CLI uses,
so what you see here is what the agent actually decided — not a mock.

    python -m vouch ui        then open http://127.0.0.1:8765
"""

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .evidence import canonical_json, seal, verify_json
from .page import PAGE
from .memory import VouchMemory
from .publish import EvidenceStore
from .trust import TrustEngine

DB = os.environ.get("VOUCH_DB", ".vouch/demo.db")


def _chain(network: str):
    try:
        from .chain import Chain

        c = Chain(network)
        return c if c.connected() else None
    except Exception:
        return None


class Handler(BaseHTTPRequestHandler):
    network = "base-sepolia"
    read_only = False

    def log_message(self, *a):  # keep the terminal clean for filming
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, default=str).encode(), "application/json")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route, query = parsed.path, parse_qs(parsed.query)
        try:
            if route == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif route == "/api/state":
                self._json(self.state())
            elif route == "/api/network":
                self._json(self.network_view(query))
            elif route == "/api/decide":
                self._json(self.decide(query))
            elif route == "/api/tamper":
                self._json(self.tamper())
            elif route == "/api/delete-test":
                self._json(self.delete_test())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # surface errors instead of hanging the page
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    # ---- endpoints -------------------------------------------------------

    def state(self) -> dict:
        if not Path(DB).exists():
            return {"ready": False, "hint": "run `python -m vouch seed` first"}
        mem = VouchMemory(DB)
        st = mem.stats()
        return {
            "ready": True,
            "network": self.network,
            "chain_live": _chain(self.network) is not None,
            "issuer": os.environ.get("VOUCH_ADDRESS", ""),
            "store": st["db_path"],
            "schema_version": st["schema_version"],
            "tier": st["tier"],
            "db_bytes": st["free_tier"]["db_size_bytes"],
            "counterparties": [
                {
                    "handle": c.get("handle"),
                    "agent_id": c.get("agent_id"),
                    "jobs_completed": c.get("jobs_completed", 0),
                    "jobs_disputed": c.get("jobs_disputed", 0),
                    "flagged": bool(mem.is_flagged(c.get("handle", ""))),
                }
                for c in mem.list_counterparties()
            ],
            "policy": mem.get_policy(),
            "evidence_files": EvidenceStore().list(),
        }

    def network_view(self, query) -> dict:
        from .network import lookup

        chain = _chain(self.network)
        if chain is None:
            return {"error": f"cannot reach {self.network}"}

        agent_id = query.get("agent_id", [None])[0]
        if not agent_id:
            suffix = self.network.replace("-", "_").upper()
            agent_id = os.environ.get(f"VOUCH_SUBJECT_AGENT_ID_{suffix}")
        if not agent_id:
            return {"error": "no agent id"}

        view = lookup(chain, int(agent_id), memory=VouchMemory(DB) if Path(DB).exists() else None)
        return {
            "agent_id": int(agent_id),
            "registry": chain.cfg["reputation"],
            "explorer": chain.cfg["explorer"],
            "error": view.error,
            "verified_disputes": view.verified_disputes,
            "mean_score": view.mean_score,
            "ratings": [
                {
                    "issuer": r.issuer,
                    "score": r.score,
                    "verified": r.verified,
                    "status": r.status,
                    "uri": r.uri,
                    "digest": r.digest,
                    "tx": r.tx,
                    "testimony": r.testimony,
                }
                for r in view.ratings
            ],
        }

    def decide(self, query) -> dict:
        handle = query.get("handle", ["swiftrender"])[0]
        price = float(query.get("price", ["25"])[0])
        offline = query.get("offline", ["0"])[0] == "1"

        # An explicit agent id lets the page ask about a counterparty we have
        # never dealt with. That is the sharpest form of the claim: with only
        # our own memory the agent knows nothing, and the network still stops
        # it walking into a bad deal.
        agent_id = query.get("agent_id", [None])[0]
        if not agent_id:
            suffix = self.network.replace("-", "_").upper()
            agent_id = os.environ.get(f"VOUCH_SUBJECT_AGENT_ID_{suffix}")

        mem = VouchMemory(DB)
        chain = None if offline else _chain(self.network)
        eng = TrustEngine(mem, chain=chain, issuer_address=os.environ.get("VOUCH_ADDRESS"))
        v = eng.decide(
            handle,
            standard_price_usd=price,
            agent_id=int(agent_id) if agent_id else None,
        )
        out = v.to_dict()
        out["offline"] = offline
        out["handle"] = handle
        return out

    def tamper(self) -> dict:
        """Run the forgery live, so the page proves it rather than claiming it."""
        store = EvidenceStore()
        files = store.list()
        if not files:
            return {"error": "no evidence files"}
        newest = max((store.dir / f for f in files), key=lambda p: p.stat().st_mtime)
        digest = "0x" + newest.stem
        original = json.loads(newest.read_bytes())

        forged = json.loads(newest.read_bytes())
        before = forged["summary"]["jobs_disputed"]
        forged["summary"]["jobs_disputed"] = 0
        forged["verdict"]["decision"] = "ACCEPT"
        forged["events"] = []

        return {
            "file": newest.name,
            "committed_hash": digest,
            "honest_verifies": verify_json(original, digest),
            "forgery": f"jobs_disputed {before} to 0, testimony removed",
            "forged_hash": seal(forged)[1],
            "forged_verifies": verify_json(forged, digest),
            "bytes": len(canonical_json(original)),
        }

    def delete_test(self) -> dict:
        """The gate, executed on request: same agent, with and without memory."""
        import tempfile

        handle = "swiftrender"
        with_mem = None
        if Path(DB).exists():
            with_mem = TrustEngine(VouchMemory(DB)).decide(handle, standard_price_usd=25.0)

        tmp = Path(tempfile.mkdtemp()) / "empty.db"
        without = TrustEngine(VouchMemory(str(tmp))).decide(handle, standard_price_usd=25.0)
        return {
            "with_memory": with_mem.to_dict() if with_mem else None,
            "without_memory": without.to_dict(),
            "differs": bool(with_mem and with_mem.decision != without.decision),
        }


def serve(
    port: int = 8765,
    network: str = "base-sepolia",
    open_browser: bool = True,
    host: str = "127.0.0.1",
    read_only: bool = False,
) -> int:
    Handler.network = network
    Handler.read_only = read_only

    # A hosted dashboard must never hold a signing key. It only ever reads, so
    # refuse to start if one is present rather than quietly carrying it.
    if read_only:
        leaked = [k for k in ("VOUCH_PRIVATE_KEY", "VOUCH_COUNTERPARTY_KEY",
                              "VOUCH_SECOND_ISSUER_KEY", "SELLER_SIGNER_PRIVATE_KEY")
                  if os.environ.get(k)]
        if leaked:
            print(f"  refusing to start read-only with keys present: {', '.join(leaked)}")
            return 2

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '') else host}:{port}"
    print(f"  Vouch dashboard on {url}   (network: {network})")
    print("  ctrl-c to stop")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()
    return 0


