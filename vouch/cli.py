"""Vouch demo CLI.

Four proofs, each runnable on its own so a judge can re-run any of them:

    python -m vouch seed         session 1: work with an agent, log what happened
    python -m vouch coldstart    session 2: fresh process, memory changes the call
    python -m vouch tamper       a forged evidence file is rejected
    python -m vouch delete-test  the gate: no memory, no product
    python -m vouch sibyl        read SIBYL's real ERC-8004 record on Base

Nothing here writes to a chain unless you pass --publish and supply a key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import DEFAULT_POLICY
from .memory import VouchMemory
from .trust import TrustEngine
from .evidence import verify_json, seal
from .publish import EvidenceStore, build_and_store, score_from_counterparty, VOUCH_TAG1, VOUCH_TAG2

DB = os.environ.get("VOUCH_DB", ".vouch/demo.db")
def issuer() -> dict:
    """Built lazily so .env is loaded first."""
    return {
        "handle": os.environ.get("VOUCH_HANDLE", "attrito.vouch"),
        "agent_id": int(os.environ["VOUCH_AGENT_ID"]) if os.environ.get("VOUCH_AGENT_ID") else None,
        "address": os.environ.get("VOUCH_ADDRESS", "0x0000000000000000000000000000000000000A11"),
    }

BOLD, DIM, RED, GRN, YEL, CYN, RST = (
    "\033[1m", "\033[2m", "\033[31m", "\033[32m", "\033[33m", "\033[36m", "\033[0m"
)


def _load_env(path: str = ".env") -> None:
    """Minimal .env loader. Real environment variables always win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _setup_console() -> None:
    """Windows terminals default to cp1252 and swallow ANSI. Fix both."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if os.name == "nt":
        try:
            import ctypes

            k = ctypes.windll.kernel32
            k.SetConsoleMode(k.GetStdHandle(-11), 7)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass


def rule(title: str) -> None:
    print(f"\n{BOLD}{CYN}{'─' * 68}{RST}")
    print(f"{BOLD}{CYN}  {title}{RST}")
    print(f"{BOLD}{CYN}{'─' * 68}{RST}")


def kv(k: str, v) -> None:
    print(f"  {DIM}{k:<22}{RST}{v}")


# ---------------------------------------------------------------- seed

def cmd_seed(args) -> int:
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    if Path(DB).exists() and not args.keep:
        Path(DB).unlink()
    mem = VouchMemory(DB)
    mem.set_policy(DEFAULT_POLICY)
    eng = TrustEngine(mem)

    rule("SESSION 1  ·  first contact, no history")
    mem.upsert_counterparty(
        "swiftrender", agent_id=4242,
        address="0x00000000000000000000000000000000SwiftR"[:42].ljust(42, "0"),
    )
    v = eng.decide("swiftrender", standard_price_usd=25.0, job_ref="job-001")
    kv("counterparty", "swiftrender (ERC-8004 #4242)")
    kv("memory says", "nothing on record")
    print(f"  {GRN}{v.headline()}{RST}")

    rule("THE JOB GOES WRONG")
    mem.upsert_counterparty("swiftrender", jobs_completed=0, jobs_disputed=1)
    mem.record_incident(
        "swiftrender", kind="dispute",
        detail="disputed job-001 after delivery was accepted, then short-paid the invoice by 60%",
        job_ref="job-001",
    )
    kv("incident logged", "dispute · job-001")
    kv("journal", "append-only, never rewritten")

    # A clean counterparty, so the demo has a control.
    mem.upsert_counterparty("pixelforge", agent_id=7331, jobs_completed=3, jobs_disputed=0)
    mem.record_incident("pixelforge", kind="note", detail="delivered job-A, job-B, job-C on time", job_ref="job-A")

    rule("SEAL THE EVIDENCE")
    store = EvidenceStore()
    # Re-decide first: the evidence must carry the verdict as it stands *after*
    # the incident, not the one made before it. Sealing a stale verdict would
    # publish "ACCEPT" alongside testimony of a dispute.
    current = eng.decide("swiftrender", standard_price_usd=25.0)
    receipt = build_and_store(store, memory=mem, handle="swiftrender", verdict=current, issuer=issuer())
    value, decimals = score_from_counterparty(mem.get_counterparty("swiftrender"))
    kv("evidence file", receipt["filename"])
    kv("bytes", receipt["bytes"])
    kv("feedbackHash", receipt["hash"])
    kv("feedbackURI", receipt["uri"])
    kv("ERC-8004 value", f"{value} (decimals={decimals}) = {value / 10**decimals:.2f}/100")

    if args.publish:
        rc = _publish(receipt, value, decimals, args)
        if rc:
            return rc

    print(f"\n  {DIM}Now run:{RST} python -m vouch coldstart")
    return 0


def _publish(receipt, value, decimals, args) -> int:
    from .chain import Chain

    key = os.environ.get("VOUCH_PRIVATE_KEY")
    agent_id = os.environ.get("VOUCH_SUBJECT_AGENT_ID")
    if not key:
        print(f"  {RED}--publish needs VOUCH_PRIVATE_KEY{RST}")
        return 2
    if not agent_id:
        print(f"  {RED}--publish needs VOUCH_SUBJECT_AGENT_ID (the agent being rated){RST}")
        return 2
    chain = Chain(args.network, private_key=key)
    rule(f"PUBLISH TO {args.network.upper()}")
    kv("registry", chain.cfg["reputation"])
    tx = chain.give_feedback(
        int(agent_id), value=value, value_decimals=decimals,
        tag1=VOUCH_TAG1, tag2=VOUCH_TAG2,
        endpoint="", feedback_uri=receipt["uri"], feedback_hash=receipt["hash"],
    )
    kv("tx", chain.explorer_tx(tx))
    return 0


# ------------------------------------------------------------ coldstart

def cmd_coldstart(args) -> int:
    if not Path(DB).exists():
        print(f"{RED}no memory at {DB} — run `python -m vouch seed` first{RST}")
        return 1

    rule("SESSION 2  ·  fresh process, empty context")
    print(f"  {DIM}This process has never seen swiftrender. Everything it knows,{RST}")
    print(f"  {DIM}it is about to read out of Sibyl Memory.{RST}\n")

    mem = VouchMemory(DB)
    eng = TrustEngine(mem)

    for handle, price in (("swiftrender", 25.0), ("pixelforge", 25.0)):
        v = eng.decide(handle, standard_price_usd=price, job_ref=f"new-{handle}")
        colour = RED if v.decision == "REFUSE" else (YEL if v.decision != "ACCEPT" else GRN)
        print(f"  {BOLD}{handle}{RST}")
        print(f"    {colour}{v.headline()}{RST}")
        for c in v.citations:
            print(f"    {DIM}cited: {c}{RST}")
        print()

    st = mem.stats()
    kv("store", st["db_path"])
    kv("counterparties", st["counterparties"])
    kv("schema version", st["schema_version"])
    return 0


# --------------------------------------------------------------- tamper

def cmd_tamper(args) -> int:
    store = EvidenceStore()
    files = store.list()
    if not files:
        print(f"{RED}no evidence files — run `python -m vouch seed` first{RST}")
        return 1

    name = files[0]
    digest = "0x" + name.removesuffix(".json")
    blob = store.get(digest)
    original = json.loads(blob)

    rule("TAMPER DETECTION")
    print(f"  {DIM}The evidence file lives on a mutable host. The hash committed{RST}")
    print(f"  {DIM}on Base is what makes editing it detectable.{RST}\n")

    kv("file", name)
    kv("on-chain hash", digest)
    kv("honest file verifies", f"{GRN}{verify_json(original, digest)}{RST}")

    forged = json.loads(blob)
    before = forged["summary"]["jobs_disputed"]
    forged["summary"]["jobs_disputed"] = 0
    forged["verdict"]["decision"] = "ACCEPT"
    forged["events"] = []
    _, forged_hash = seal(forged)

    print()
    kv("forgery", f"jobs_disputed {before} -> 0, events scrubbed")
    kv("forged hash", forged_hash)
    kv("forged verifies", f"{RED}{verify_json(forged, digest)}{RST}")
    print(f"\n  {GRN}Rejected.{RST} A consumer of this rating would discard it as unverified.")
    return 0


# ---------------------------------------------------------- delete test

def cmd_delete_test(args) -> int:
    rule("THE GATE  ·  delete the memory layer")
    print(f"  {DIM}Same code, same counterparty, same request. The only difference{RST}")
    print(f"  {DIM}is that memory is gone.{RST}\n")

    if Path(DB).exists():
        mem = VouchMemory(DB)
        eng = TrustEngine(mem)
        v = eng.decide("swiftrender", standard_price_usd=25.0)
        print(f"  {BOLD}with memory   {RST} {RED}{v.headline()}{RST}")
    else:
        print(f"  {YEL}(no seeded store; run `python -m vouch seed` for the full contrast){RST}")

    tmp = Path(".vouch/_empty.db")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    if tmp.exists():
        tmp.unlink()
    with VouchMemory(str(tmp)) as mem2:
        mem2.set_policy(DEFAULT_POLICY)
        v2 = TrustEngine(mem2).decide("swiftrender", standard_price_usd=25.0)
    print(f"  {BOLD}without memory{RST} {YEL}{v2.headline()}{RST}")

    print(f"""
  {DIM}Without memory Vouch cannot tell a counterparty that burned it from one
  it has never met. There is no verdict to publish, nothing to serialise, and
  nothing to hash. The product does not degrade. It stops existing.{RST}""")
    tmp.unlink(missing_ok=True)
    return 0


# ---------------------------------------------------------------- sibyl

def cmd_sibyl(args) -> int:
    from .chain import Chain, SIBYL_AGENT_ID

    rule("LIVE  ·  SIBYL's own reputation on Base mainnet")
    chain = Chain("base")
    if not chain.connected():
        print(f"{RED}could not reach Base mainnet{RST}")
        return 1

    kv("agent id", SIBYL_AGENT_ID)
    kv("identity registry", chain.cfg["identity"])
    kv("reputation registry", chain.cfg["reputation"])
    try:
        kv("owner", chain.identity.functions.ownerOf(SIBYL_AGENT_ID).call())
        kv("agentURI", chain.identity.functions.tokenURI(SIBYL_AGENT_ID).call())
    except Exception as e:
        kv("identity read", f"{RED}{type(e).__name__}{RST}")

    clients = chain.clients(SIBYL_AGENT_ID)
    kv("clients", len(clients))
    cl, idx, vals, decs, t1, t2, rev = chain.reputation.functions.readAllFeedback(
        SIBYL_AGENT_ID, clients, "", "", False
    ).call()
    kv("feedback entries", len(cl))

    print(f"\n  {BOLD}The scales do not agree:{RST}")
    seen = {}
    for i in range(len(cl)):
        seen.setdefault((vals[i], decs[i], t1[i]), 0)
        seen[(vals[i], decs[i], t1[i])] += 1
    for (v, d, tag), n in sorted(seen.items(), key=lambda x: -x[1])[:8]:
        print(f"    value={v:<6} decimals={d}  -> {v / (10**d) if d else float(v):<8} tag1={tag!r} ({n}x)")

    scores = [vals[i] / (10 ** decs[i]) if decs[i] else float(vals[i]) for i in range(len(cl))]
    if scores:
        print(f"\n  {YEL}Range {min(scores)} to {max(scores)}. Mean {sum(scores)/len(scores):.2f} —")
        print(f"  arithmetic across 0-1, 0-5 and 0-100 scales. The number means nothing.{RST}")
    print(f"\n  {DIM}Vouch fixes the scale (0-100, 2 decimals) and attaches the evidence.{RST}")
    return 0


# ------------------------------------------------- machine-readable API
# These three commands are the integration surface. Any agent in any language
# can shell out to them; the ACP bridge in acp/ does exactly that.


def cmd_decide(args) -> int:
    """Should I take this job? Reads memory, returns a verdict as JSON."""
    with VouchMemory(args.db or DB) as mem:
        verdict = TrustEngine(mem).decide(
            args.handle, standard_price_usd=args.price, job_ref=args.job_ref
        )
    out = verdict.to_dict()
    out["headline"] = verdict.headline()
    print(json.dumps(out, indent=None if args.compact else 2))
    return 0


def cmd_record(args) -> int:
    """Log what a counterparty did. This is the write that makes the next call differ."""
    with VouchMemory(args.db or DB) as mem:
        mem.upsert_counterparty(args.handle, agent_id=args.agent_id, address=args.address)
        if args.kind in ("dispute", "fraud", "nonpayment"):
            cp = mem.get_counterparty(args.handle) or {}
            mem.upsert_counterparty(
                args.handle, jobs_disputed=int(cp.get("jobs_disputed", 0)) + 1
            )
        elif args.kind == "completed":
            cp = mem.get_counterparty(args.handle) or {}
            mem.upsert_counterparty(
                args.handle, jobs_completed=int(cp.get("jobs_completed", 0)) + 1
            )
        event_id = mem.record_incident(
            args.handle, kind=args.kind, detail=args.detail, job_ref=args.job_ref
        )
        if args.flag:
            mem.flag(args.handle, reason=args.detail)
        cp = mem.get_counterparty(args.handle)
    print(json.dumps({"event_id": event_id, "counterparty": cp}, indent=2))
    return 0


def cmd_rate(args) -> int:
    """Build the evidence file for a counterparty and optionally publish it."""
    with VouchMemory(args.db or DB) as mem:
        verdict = TrustEngine(mem).decide(args.handle, standard_price_usd=args.price)
        store = EvidenceStore()
        receipt = build_and_store(
            store, memory=mem, handle=args.handle, verdict=verdict, issuer=issuer()
        )
        cp = mem.get_counterparty(args.handle) or {}
    value, decimals = score_from_counterparty(cp)
    result = {
        "handle": args.handle,
        "score": value / 10**decimals,
        "erc8004": {
            "value": value,
            "valueDecimals": decimals,
            "tag1": VOUCH_TAG1,
            "tag2": VOUCH_TAG2,
            "feedbackURI": receipt["uri"],
            "feedbackHash": receipt["hash"],
        },
        "evidence_path": receipt["path"],
        "bytes": receipt["bytes"],
        "published": False,
    }
    if args.publish:
        from .chain import Chain

        key = os.environ.get("VOUCH_PRIVATE_KEY")
        subject = args.subject_agent_id or os.environ.get("VOUCH_SUBJECT_AGENT_ID")
        if not key or not subject:
            result["error"] = "publishing needs VOUCH_PRIVATE_KEY and --subject-agent-id"
            print(json.dumps(result, indent=2))
            return 2
        chain = Chain(args.network, private_key=key)
        tx = chain.give_feedback(
            int(subject), value=value, value_decimals=decimals,
            tag1=VOUCH_TAG1, tag2=VOUCH_TAG2, endpoint="",
            feedback_uri=receipt["uri"], feedback_hash=receipt["hash"],
        )
        result["published"] = True
        result["tx"] = tx
        result["explorer"] = chain.explorer_tx(tx)
    print(json.dumps(result, indent=2))
    return 0


def cmd_lookup(args) -> int:
    """What does memory know about this counterparty? JSON, for other agents."""
    with VouchMemory(args.db or DB) as mem:
        cp = mem.get_counterparty(args.handle)
        flagged = mem.is_flagged(args.handle)
        incidents = mem.incidents(args.handle)
    print(json.dumps({
        "handle": args.handle,
        "known": cp is not None,
        "counterparty": cp,
        "flagged": flagged,
        "incidents": [
            {"ts": e.get("ts") or e.get("created_at"),
             "kind": (e.get("extra") or {}).get("kind"),
             "acted": e.get("acted")}
            for e in incidents
        ],
    }, indent=2, default=str))
    return 0


# ------------------------------------------------------------------ main

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vouch", description="Vouch — the vouching layer for agents")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seed", help="session 1: work with an agent and log it")
    s.add_argument("--keep", action="store_true", help="append to an existing store")
    s.add_argument("--publish", action="store_true", help="write the rating on-chain")
    s.add_argument("--network", default="base-sepolia", choices=["base", "base-sepolia", "ethereum-sepolia"])
    s.set_defaults(func=cmd_seed)

    for name, fn, helptext in (
        ("coldstart", cmd_coldstart, "session 2: fresh process, memory changes the call"),
        ("tamper", cmd_tamper, "show a forged evidence file being rejected"),
        ("delete-test", cmd_delete_test, "the gate: no memory, no product"),
        ("sibyl", cmd_sibyl, "read SIBYL's real ERC-8004 record on Base"),
    ):
        q = sub.add_parser(name, help=helptext)
        q.set_defaults(func=fn)

    # --- machine-readable API (the adapter surface) ---
    d = sub.add_parser("decide", help="[json] should I take this job?")
    d.add_argument("--handle", required=True)
    d.add_argument("--price", type=float, default=0.0)
    d.add_argument("--job-ref", default=None)
    d.add_argument("--db", default=None)
    d.add_argument("--compact", action="store_true")
    d.set_defaults(func=cmd_decide)

    r = sub.add_parser("record", help="[json] log what a counterparty did")
    r.add_argument("--handle", required=True)
    r.add_argument("--kind", required=True,
                   choices=["dispute", "fraud", "nonpayment", "completed", "note"])
    r.add_argument("--detail", required=True)
    r.add_argument("--job-ref", default=None)
    r.add_argument("--agent-id", type=int, default=None)
    r.add_argument("--address", default=None)
    r.add_argument("--flag", action="store_true", help="also add to the FLAGGED tier")
    r.add_argument("--db", default=None)
    r.set_defaults(func=cmd_record)

    ra = sub.add_parser("rate", help="[json] build the evidence file, optionally publish")
    ra.add_argument("--handle", required=True)
    ra.add_argument("--price", type=float, default=0.0)
    ra.add_argument("--publish", action="store_true")
    ra.add_argument("--subject-agent-id", type=int, default=None)
    ra.add_argument("--network", default="base-sepolia", choices=["base", "base-sepolia", "ethereum-sepolia"])
    ra.add_argument("--db", default=None)
    ra.set_defaults(func=cmd_rate)

    lk = sub.add_parser("lookup", help="[json] what does memory know about this agent?")
    lk.add_argument("--handle", required=True)
    lk.add_argument("--db", default=None)
    lk.set_defaults(func=cmd_lookup)

    _load_env()
    _setup_console()
    args = p.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
