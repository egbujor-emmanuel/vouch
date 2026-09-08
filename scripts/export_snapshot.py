#!/usr/bin/env python
"""Export what the static dashboard needs, and nothing it doesn't.

The hosted page verifies everything itself: it reads the registry over RPC,
fetches each evidence file, and re-hashes it in the browser. This snapshot
carries only local memory (which the browser cannot read) plus block-number
hints so the page can find the right logs in one call instead of forty.

Nothing here is trusted by the page. The hints are checked against the chain,
and if a hint is wrong the rating simply shows as unverified.

    python scripts/export_snapshot.py --network base-sepolia
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from vouch.chain import Chain  # noqa: E402
from vouch.memory import VouchMemory  # noqa: E402
from vouch.publish import EvidenceStore  # noqa: E402
from vouch.trust import TrustEngine  # noqa: E402

OUT = Path("docs/snapshot.json")

# A judge gets one look at the page. Public endpoints rate-limit, and a single
# throttled request is enough to render an agent with two filings as having
# none — which is exactly the failure this project exists to complain about.
# All three answer with permissive CORS.
RPCS = {
    "base-sepolia": [
        "https://sepolia.base.org",
        "https://base-sepolia-rpc.publicnode.com",
        "https://base-sepolia.drpc.org",
    ],
    "base": ["https://mainnet.base.org", "https://base-rpc.publicnode.com"],
}


def load_env(path=".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _response_hints(network: str, agent_id: int) -> list:
    """Block numbers for any appendResponse filed against this agent."""
    import json as _json

    try:
        idx = _json.loads(Path("filings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return idx.get(network, {}).get("responses", {}).get(str(agent_id), [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", default="base-sepolia")
    args = ap.parse_args()

    load_env()
    suffix = args.network.replace("-", "_").upper()
    subject = int(os.environ.get(f"VOUCH_SUBJECT_AGENT_ID_{suffix}", "0") or 0)
    db = os.environ.get("VOUCH_DB", ".vouch/memory.db")

    if not Path(db).exists():
        print(f"no memory at {db} — run `python -m vouch seed` first")
        return 1

    mem = VouchMemory(db)
    chain = Chain(args.network)

    # Block-number hints, so the browser can fetch each NewFeedback log with a
    # narrow range instead of walking the chain.
    hints = []
    for r in chain.ratings(subject, memory=mem):
        if r.get("block"):
            hints.append({
                "client": r["client"],
                "index": r["index"],
                "block": r["block"],
                "uri": r["feedback_uri"],
            })

    # Both verdicts, computed here so the page can show the comparison even
    # before its own live lookup finishes. The page recomputes verification
    # itself; these are for first paint only.
    # Verify once here so the snapshot can carry the answer.
    from vouch.network import lookup

    filings = []
    view = lookup(chain, subject, memory=mem)
    for r in view.ratings:
        filings.append({
            "issuer": r.issuer,
            "score": r.score,
            "verified": r.verified,
            "status": r.status,
            "uri": r.uri,
            "hash": r.digest,
            "tx": r.tx,
            "index": r.index,
            "testimony": r.testimony,
            "disputes": r.disputes,
        })

    engine_offline = TrustEngine(mem)
    stranger_offline = engine_offline.decide("newcomer", standard_price_usd=25.0)
    known_offline = engine_offline.decide("swiftrender", standard_price_usd=25.0)

    snap = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "network": {
            "name": args.network,
            "chain_id": chain.cfg["chain_id"],
            "rpc": "https://sepolia.base.org",
            "rpcs": RPCS.get(args.network, [chain.cfg["rpc"]]),
            "explorer": chain.cfg["explorer"],
            "reputation": chain.cfg["reputation"],
            "identity": chain.cfg["identity"],
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
                    "handle": c.get("handle"),
                    "agent_id": c.get("agent_id"),
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
            "newcomer": stranger_offline.to_dict(),
            "swiftrender": known_offline.to_dict(),
        },
        # Pre-verified filings, so the page paints the moment it loads instead
        # of sitting on a spinner for half a minute while public RPCs answer.
        # These are a first impression only: the browser re-fetches every file
        # and recomputes every seal, then replaces this with its own result. If
        # the two ever disagree the browser wins, visibly.
        "filings": filings,
        # Where the right of reply lives. Without this the page walked 40,000
        # blocks looking for it — fifty sequential requests, and the single
        # biggest reason the page felt slow.
        "response_hints": _response_hints(args.network, subject),
        "log_hints": hints,
        "evidence_base_url": os.environ.get("VOUCH_EVIDENCE_BASE_URL", ""),
        "evidence_files": EvidenceStore().list(),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"  counterparties {len(snap['memory']['counterparties'])}"
          f" · incidents {len(snap['memory']['incidents'])}"
          f" · log hints {len(hints)}")

    # A snapshot must never carry a key. Check rather than assume.
    blob = OUT.read_text(encoding="utf-8")
    for probe in ("PRIVATE_KEY", "SIGNER", os.environ.get("VOUCH_PRIVATE_KEY", "\0nope")):
        if probe and probe != "\0nope" and probe in blob:
            print(f"  REFUSING: snapshot contains a secret ({probe[:12]}…)")
            OUT.unlink()
            return 2
    print("  no secrets in snapshot")
    return 0


if __name__ == "__main__":
    sys.exit(main())
