"""Guards on the things that break silently outside Python.

A malformed deploy config does not fail a build loudly; the host simply
rejects it and serves nothing, which is how vercel.json shipped with an
invalid JSON escape and stopped the site deploying while GitHub Pages, which
never reads that file, carried on fine.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def json_files():
    out = []
    for pattern in ("*.json", "agents/*.json", "docs/*.json", "acp/package.json", "evidence/*.json"):
        out.extend(sorted(ROOT.glob(pattern)))
    return out


@pytest.mark.parametrize("path", json_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_every_json_file_parses(path):
    json.loads(path.read_text(encoding="utf-8"))


def test_vercel_config_serves_the_static_directory():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["outputDirectory"] == "docs"
    # A null framework plus explicit no-op commands is what stops Vercel
    # detecting the Python package and looking for a serverless entrypoint.
    assert cfg["framework"] is None
    assert cfg["buildCommand"]
    assert cfg["installCommand"]


def test_the_published_site_is_self_contained():
    """Every script the page loads must exist in docs/."""
    html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    import re

    for src in re.findall(r'<script src="([^"]+)"', html):
        if src.startswith("http"):
            pytest.fail(f"page loads an external script: {src}")
        assert (ROOT / "docs" / src).is_file(), f"missing {src}"


def test_no_secret_reaches_the_published_directory():
    """Nothing under docs/ may carry a key, however it got there."""
    markers = ("PRIVATE_KEY", "SIGNER_PRIVATE", "BEGIN PRIVATE", "MIGHAgEA")
    for path in (ROOT / "docs").rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in markers:
            assert m not in text, f"{path.name} contains {m}"


def test_evidence_files_are_named_by_their_own_digest():
    """Content addressing is the invariant that keeps URI and seal aligned."""
    from vouch.evidence import hash_hex

    for path in (ROOT / "evidence").glob("*.json"):
        assert hash_hex(path.read_bytes()) == "0x" + path.stem, path.name


class TestFilingsStayFindable:
    """Regression: a filing aged out of the RPC log window and vanished.

    Evidence pointers live only in NewFeedback logs, and public RPCs cap how
    far back a log query reaches — about a day on Base Sepolia. Our first
    filing crossed that boundary roughly 23 hours after it was made and started
    reporting "no evidence attached", which is indistinguishable from a rating
    that never had evidence: precisely the failure this project objects to.
    """

    def test_the_index_covers_every_published_filing(self):
        import json as _json

        index = ROOT / "filings.json"
        assert index.is_file(), "filings.json is what keeps old filings findable"
        data = _json.loads(index.read_text(encoding="utf-8"))

        entries = data.get("base-sepolia", {}).get("filings", {}).get("9178", [])
        assert len(entries) >= 2, "both published filings must be indexed"
        for e in entries:
            assert e["block"] > 0, "a hint without a block cannot locate anything"
            assert e["uri"].startswith("https://"), e
            assert e["client"].startswith("0x")

    def test_every_indexed_uri_has_its_evidence_file(self):
        """A hint pointing at a file we no longer ship would resolve to nothing."""
        import json as _json

        data = _json.loads((ROOT / "filings.json").read_text(encoding="utf-8"))
        for network in data.values():
            for entries in network.get("filings", {}).values():
                for e in entries:
                    name = e["uri"].rsplit("/", 1)[-1]
                    assert (ROOT / "evidence" / name).is_file(), f"missing {name}"

    def test_hints_are_not_trusted_blindly(self):
        """The index must only ever locate; it must never assert a seal."""
        src = (ROOT / "vouch" / "filings.py").read_text(encoding="utf-8")
        assert "feedback_hash" not in src, (
            "storing a seal in the index would create a second copy that could "
            "disagree with the chain"
        )
