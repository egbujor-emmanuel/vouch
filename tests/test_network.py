"""The network layer: believing other agents only when the maths says so.

These tests use a fake chain and a fake HTTP fetch, so they run offline and
deterministically. What they protect is the rule that makes Vouch worth
anything: unverified evidence is never counted.
"""

from __future__ import annotations

import json

import pytest

from vouch import network as net
from vouch.evidence import canonical_json, seal
from vouch.memory import VouchMemory, DEFAULT_POLICY
from vouch.trust import ACCEPT_WITH_ESCROW, REFUSE, TrustEngine

ISSUER_A = "0xAAaaAAaaAAaaAAaaAAaaAAaaAAaaAAaaAAaaAAaa"
ISSUER_B = "0xBBbbBBbbBBbbBBbbBBbbBBbbBBbbBBbbBBbbBBbb"


def make_evidence(disputed=1, completed=0, detail="abandoned the job mid-delivery"):
    return {
        "schema": "vouch.evidence/v1",
        "issued_at": "2026-09-05T00:00:00Z",
        "issuer": {"handle": "northgate.vouch", "agent_id": None, "address": ISSUER_B},
        "subject": {"handle": "swiftrender", "agent_id": 9178, "address": "0xcafe"},
        "summary": {
            "jobs_completed": completed,
            "jobs_disputed": disputed,
            "total_value_usd": 40.0,
            "first_seen": "2026-09-01T00:00:00Z",
            "last_seen": "2026-09-04T00:00:00Z",
        },
        "verdict": {"decision": "REFUSE", "reason": "disputed"},
        "events": [{"ts": "2026-09-04T00:00:00Z", "acted": [detail]}],
    }


class FakeChain:
    """Stands in for Chain.feedback_uris with whatever the test needs."""

    def __init__(self, entries):
        self._entries = entries

    def feedback_uris(self, agent_id, from_block=None):
        return list(self._entries)


def entry(uri, digest, *, client=ISSUER_B, value=0, decimals=2, tx="0xtx"):
    return {
        "client": client, "index": 0, "value": value, "value_decimals": decimals,
        "tag1": "vouch", "tag2": "counterparty-conduct", "endpoint": "",
        "feedback_uri": uri, "feedback_hash": digest, "tx": tx, "block": 1,
    }


@pytest.fixture
def served(monkeypatch):
    """Route network._fetch at an in-memory dict of URI -> bytes."""
    files: dict[str, bytes] = {}

    def fake_fetch(uri):
        if uri not in files:
            raise OSError("404")
        return files[uri]

    monkeypatch.setattr(net, "_fetch", fake_fetch)
    return files


class TestVerification:
    def test_matching_evidence_is_believed(self, served):
        ev = make_evidence()
        blob, digest = seal(ev)
        served["https://x/e.json"] = blob
        view = net.lookup(FakeChain([entry("https://x/e.json", digest)]), 9178)
        assert len(view.verified) == 1
        assert view.verified[0].status == "verified"
        assert view.verified_disputes == 1

    def test_altered_evidence_is_discarded(self, served):
        ev = make_evidence()
        _, digest = seal(ev)
        ev["summary"]["jobs_disputed"] = 0  # forge it after committing the hash
        served["https://x/e.json"] = canonical_json(ev)
        view = net.lookup(FakeChain([entry("https://x/e.json", digest)]), 9178)
        assert view.verified == []
        assert "HASH MISMATCH" in view.rejected[0].status
        assert view.verified_disputes == 0

    def test_missing_evidence_file_is_discarded(self, served):
        _, digest = seal(make_evidence())
        view = net.lookup(FakeChain([entry("https://x/gone.json", digest)]), 9178)
        assert view.verified == []
        assert "unreachable" in view.rejected[0].status

    def test_rating_with_no_evidence_pointer_is_discarded(self, served):
        # This is the status quo Vouch exists to fix: a number with nothing
        # behind it. It must never count.
        view = net.lookup(FakeChain([entry("", "0x" + "00" * 32)]), 9178)
        assert view.verified == []
        assert view.rejected[0].status == "no evidence attached"

    def test_zero_hash_is_treated_as_no_evidence(self, served):
        served["https://x/e.json"] = canonical_json(make_evidence())
        view = net.lookup(FakeChain([entry("https://x/e.json", "0x" + "00" * 32)]), 9178)
        assert view.verified == []

    def test_malformed_json_is_discarded(self, served):
        served["https://x/e.json"] = b"{not json"
        _, digest = seal(make_evidence())
        view = net.lookup(FakeChain([entry("https://x/e.json", digest)]), 9178)
        assert "not valid JSON" in view.rejected[0].status

    def test_non_http_uri_is_refused(self, served):
        _, digest = seal(make_evidence())
        view = net.lookup(FakeChain([entry("file:///etc/passwd", digest)]), 9178)
        assert view.verified == []
        assert "unreachable" in view.rejected[0].status

    def test_our_own_ratings_are_excluded(self, served):
        ev = make_evidence()
        blob, digest = seal(ev)
        served["https://x/e.json"] = blob
        chain = FakeChain([entry("https://x/e.json", digest, client=ISSUER_A)])
        view = net.lookup(chain, 9178, exclude_issuer=ISSUER_A)
        assert view.ratings == []

    def test_exclusion_is_case_insensitive(self, served):
        ev = make_evidence()
        blob, digest = seal(ev)
        served["https://x/e.json"] = blob
        chain = FakeChain([entry("https://x/e.json", digest, client=ISSUER_A.lower())])
        view = net.lookup(chain, 9178, exclude_issuer=ISSUER_A.upper())
        assert view.ratings == []

    def test_a_broken_chain_read_degrades_to_empty(self):
        class Broken:
            def feedback_uris(self, agent_id, from_block=None):
                raise RuntimeError("rpc down")

        view = net.lookup(Broken(), 9178)
        assert view.ratings == []
        assert view.verified_disputes == 0


class TestTestimony:
    def test_verified_testimony_is_readable(self, served):
        blob, digest = seal(make_evidence(detail="vanished after escrow released"))
        served["https://x/e.json"] = blob
        view = net.lookup(FakeChain([entry("https://x/e.json", digest)]), 9178)
        assert any("vanished after escrow" in t for t in view.testimony())

    def test_unverified_testimony_is_not_offered(self, served):
        ev = make_evidence(detail="fabricated smear")
        _, digest = seal(ev)
        ev["events"][0]["acted"] = ["fabricated smear"]
        ev["summary"]["jobs_disputed"] = 99
        served["https://x/e.json"] = canonical_json(ev)
        view = net.lookup(FakeChain([entry("https://x/e.json", digest)]), 9178)
        assert view.testimony() == []


class TestDecisionsUseTheNetwork:
    """The point of publishing: one agent acts on another's experience."""

    def test_stranger_is_refused_on_someone_elses_verified_evidence(self, tmp_path, served):
        blob, digest = seal(make_evidence(disputed=2))
        served["https://x/e.json"] = blob
        chain = FakeChain([entry("https://x/e.json", digest)])

        mem = VouchMemory(str(tmp_path / "n.db"))
        mem.set_policy(DEFAULT_POLICY)
        assert mem.get_counterparty("swiftrender") is None  # never met them

        v = TrustEngine(mem, chain=chain, issuer_address=ISSUER_A).decide(
            "swiftrender", standard_price_usd=25.0, agent_id=9178
        )
        assert v.decision == REFUSE
        assert v.evidence_checked is True
        assert v.evidence_verified is True
        assert "verified" in v.reason

    def test_stranger_is_not_refused_on_unverifiable_evidence(self, tmp_path, served):
        ev = make_evidence(disputed=2)
        _, digest = seal(ev)
        ev["summary"]["jobs_disputed"] = 99
        served["https://x/e.json"] = canonical_json(ev)  # forged
        chain = FakeChain([entry("https://x/e.json", digest)])

        mem = VouchMemory(str(tmp_path / "n2.db"))
        mem.set_policy(DEFAULT_POLICY)
        v = TrustEngine(mem, chain=chain, issuer_address=ISSUER_A).decide(
            "swiftrender", standard_price_usd=25.0, agent_id=9178
        )
        assert v.decision == ACCEPT_WITH_ESCROW
        assert v.evidence_checked is True
        assert v.evidence_verified is False

    def test_network_disputes_add_to_our_own(self, tmp_path, served):
        blob, digest = seal(make_evidence(disputed=1))
        served["https://x/e.json"] = blob
        chain = FakeChain([entry("https://x/e.json", digest)])

        mem = VouchMemory(str(tmp_path / "n3.db"))
        mem.set_policy(DEFAULT_POLICY)
        # On our books alone this is 1-in-21: escrow, not refusal.
        mem.upsert_counterparty("swiftrender", agent_id=9178, jobs_completed=20, jobs_disputed=1)
        alone = TrustEngine(mem).decide("swiftrender", standard_price_usd=25.0)
        assert alone.decision == ACCEPT_WITH_ESCROW

        withnet = TrustEngine(mem, chain=chain, issuer_address=ISSUER_A).decide(
            "swiftrender", standard_price_usd=25.0
        )
        assert withnet.evidence_checked is True
        assert "network" in withnet.reason

    def test_network_lookup_is_skippable(self, tmp_path, served):
        blob, digest = seal(make_evidence(disputed=2))
        served["https://x/e.json"] = blob
        chain = FakeChain([entry("https://x/e.json", digest)])
        mem = VouchMemory(str(tmp_path / "n4.db"))
        mem.set_policy(DEFAULT_POLICY)
        v = TrustEngine(mem, chain=chain).decide(
            "swiftrender", standard_price_usd=25.0, agent_id=9178, use_network=False
        )
        assert v.evidence_checked is False
        assert v.decision == ACCEPT_WITH_ESCROW


class TestFailuresAreNeverSilent:
    """Regression: a failed lookup once looked identical to a clean record.

    The public Base Sepolia RPC answers wide eth_getLogs ranges with HTTP 413.
    lookup() swallowed that and returned zero ratings, so an agent with two
    published disputes read as spotless. Silence is the dangerous failure.
    """

    def test_lookup_failure_is_reported_not_hidden(self):
        class Broken:
            def ratings(self, agent_id, **kw):
                raise RuntimeError("413 Payload Too Large")

        view = net.lookup(Broken(), 9178)
        assert view.error is not None
        assert "413" in view.error
        assert view.ratings == []

    def test_a_genuinely_empty_record_has_no_error(self):
        class Empty:
            def ratings(self, agent_id, **kw):
                return []

        view = net.lookup(Empty(), 9178)
        assert view.error is None
        assert view.ratings == []

    def test_storage_backed_read_is_preferred_over_logs(self, served):
        """ratings() avoids the block-range limits that break feedback_uris()."""
        blob, digest = seal(make_evidence())
        served["https://x/e.json"] = blob
        calls = {"ratings": 0, "logs": 0}

        class Both:
            def ratings(self, agent_id, **kw):
                calls["ratings"] += 1
                return [entry("https://x/e.json", digest)]

            def feedback_uris(self, agent_id, from_block=None):
                calls["logs"] += 1
                raise AssertionError("should not fall back to logs")

        view = net.lookup(Both(), 9178)
        assert calls == {"ratings": 1, "logs": 0}
        assert len(view.verified) == 1
