"""A durable index of where filings live.

The evidence pointer for a rating exists only in the NewFeedback log, and
public RPCs cap how far back a log query may reach — on Base Sepolia roughly a
day's worth of blocks. So a filing older than that becomes unfindable by
scanning, and the rating degrades to "no evidence attached": indistinguishable,
to anyone reading, from a rating that never had evidence at all.

That is the precise failure this project exists to complain about, so it must
not happen to our own record. This module keeps a small committed index of
block numbers, checked into the repository, so a pointer stays findable however
old it gets.

The index is a hint and never a source of truth. Every entry is still fetched
from the chain at the block it names and re-hashed against what the registry
holds; a wrong or stale hint finds no log and the rating simply shows as
unverified. Nothing here can make an unverifiable filing look verified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

INDEX = Path(__file__).resolve().parent.parent / "filings.json"


def _load() -> dict[str, Any]:
    if not INDEX.exists():
        return {}
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def hints(network: str, agent_id: int) -> list[dict[str, Any]]:
    """Known block numbers for an agent's filings on a network."""
    data = _load()
    return list(data.get(network, {}).get(str(agent_id), []))


def remember(network: str, agent_id: int, entries: list[dict[str, Any]]) -> int:
    """Record where filings were found, so they stay findable.

    Only the locating information is kept — client, index, block, uri. The
    evidence itself lives at the uri and the seal lives on chain; duplicating
    either here would create a second copy that could disagree with them.
    """
    data = _load()
    net = data.setdefault(network, {})
    known = {(e["client"].lower(), e["index"]): e for e in net.get(str(agent_id), [])}

    added = 0
    for e in entries:
        if not e.get("block"):
            continue
        key = (e["client"].lower(), e["index"])
        if key in known:
            continue
        known[key] = {
            "client": e["client"],
            "index": e["index"],
            "block": e["block"],
            "uri": e.get("feedback_uri", ""),
        }
        added += 1

    if added:
        net[str(agent_id)] = sorted(known.values(), key=lambda x: x["block"])
        INDEX.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return added
