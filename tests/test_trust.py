"""The decision engine, including the gate the hackathon judges on.

The load-bearing claim is testable, so it is tested: the same code against the
same counterparty must produce a different decision with and without memory.
"""

from __future__ import annotations

import pytest

from vouch.memory import VouchMemory, DEFAULT_POLICY
from vouch.trust import ACCEPT, ACCEPT_WITH_ESCROW, REFUSE, REPRICE, TrustEngine


@pytest.fixture
def mem(tmp_path):
    m = VouchMemory(str(tmp_path / "t.db"))
    m.set_policy(DEFAULT_POLICY)
    yield m
    try:
        m.close()
    except Exception:
        pass


@pytest.fixture
def engine(mem):
    return TrustEngine(mem)


class TestTheGate:
    """Delete the memory layer and the product must stop working."""

    def test_same_agent_is_refused_with_memory_and_accepted_without(self, tmp_path):
        remembered = VouchMemory(str(tmp_path / "a.db"))
        remembered.set_policy(DEFAULT_POLICY)
        remembered.upsert_counterparty("rogue", jobs_completed=0, jobs_disputed=1)
        remembered.record_incident("rogue", kind="dispute", detail="short-paid job-1")
        with_memory = TrustEngine(remembered).decide("rogue", standard_price_usd=25.0)

        empty = VouchMemory(str(tmp_path / "b.db"))
        empty.set_policy(DEFAULT_POLICY)
        without_memory = TrustEngine(empty).decide("rogue", standard_price_usd=25.0)

        assert with_memory.decision == REFUSE
        assert without_memory.decision != REFUSE
        assert with_memory.decision != without_memory.decision

    def test_without_memory_every_counterparty_looks_identical(self, tmp_path):
        empty = VouchMemory(str(tmp_path / "c.db"))
        empty.set_policy(DEFAULT_POLICY)
        eng = TrustEngine(empty)
        a = eng.decide("saint", standard_price_usd=10.0)
        b = eng.decide("fraudster", standard_price_usd=10.0)
        assert a.decision == b.decision
        assert a.quoted_price_usd == b.quoted_price_usd


class TestDecisions:
    def test_unknown_counterparty_gets_escrow(self, engine):
        v = engine.decide("stranger", standard_price_usd=25.0)
        assert v.decision == ACCEPT_WITH_ESCROW
        assert v.escrow_required is True

    def test_clean_record_is_accepted_at_standard_terms(self, mem, engine):
        mem.upsert_counterparty("clean", jobs_completed=5, jobs_disputed=0)
        v = engine.decide("clean", standard_price_usd=25.0)
        assert v.decision == ACCEPT
        assert v.quoted_price_usd == 25.0
        assert v.escrow_required is False

    def test_heavily_disputed_is_refused(self, mem, engine):
        mem.upsert_counterparty("rogue", jobs_completed=0, jobs_disputed=2)
        v = engine.decide("rogue", standard_price_usd=25.0)
        assert v.decision == REFUSE
        assert v.quoted_price_usd == 0.0

    def test_moderately_disputed_is_repriced_not_refused(self, mem, engine):
        # 1 dispute in 4 jobs: 25%, over the reprice threshold, under decline.
        mem.upsert_counterparty("shaky", jobs_completed=3, jobs_disputed=1)
        v = engine.decide("shaky", standard_price_usd=25.0)
        assert v.decision == REPRICE
        assert v.quoted_price_usd == 50.0
        assert v.escrow_required is True

    def test_one_dispute_among_many_still_requires_escrow(self, mem, engine):
        mem.upsert_counterparty("mostly-fine", jobs_completed=20, jobs_disputed=1)
        v = engine.decide("mostly-fine", standard_price_usd=25.0)
        assert v.decision == ACCEPT_WITH_ESCROW
        assert v.escrow_required is True

    def test_flag_beats_an_otherwise_spotless_record(self, mem, engine):
        mem.upsert_counterparty("wolf", jobs_completed=50, jobs_disputed=0)
        mem.flag("wolf", reason="impersonated a known agent")
        v = engine.decide("wolf", standard_price_usd=25.0)
        assert v.decision == REFUSE
        assert "impersonated" in v.reason


class TestPolicyIsMemory:
    """The rules live in the REFERENCE tier; editing them changes behaviour."""

    def test_raising_the_threshold_turns_a_refusal_into_a_trade(self, mem):
        mem.upsert_counterparty("rogue", jobs_completed=0, jobs_disputed=2)
        assert TrustEngine(mem).decide("rogue", standard_price_usd=25.0).decision == REFUSE

        policy = dict(DEFAULT_POLICY)
        policy["dispute_ratio_decline"] = 1.01  # never decline on ratio
        policy["dispute_ratio_reprice"] = 1.01  # never reprice either
        mem.set_policy(policy)
        assert TrustEngine(mem).decide("rogue", standard_price_usd=25.0).decision != REFUSE

    def test_reprice_multiplier_is_read_from_policy(self, mem):
        mem.upsert_counterparty("shaky", jobs_completed=3, jobs_disputed=1)
        policy = dict(DEFAULT_POLICY)
        policy["reprice_multiplier"] = 3.0
        mem.set_policy(policy)
        v = TrustEngine(mem).decide("shaky", standard_price_usd=10.0)
        assert v.quoted_price_usd == 30.0

    def test_unknown_counterparty_posture_is_configurable(self, mem):
        policy = dict(DEFAULT_POLICY)
        policy["unknown_counterparty"] = "accept"
        mem.set_policy(policy)
        v = TrustEngine(mem).decide("stranger", standard_price_usd=25.0)
        assert v.decision == ACCEPT


class TestJournalling:
    def test_every_decision_is_written_to_the_journal(self, mem, engine):
        before = len(mem.m.read_events(limit=200))
        engine.decide("someone", standard_price_usd=25.0)
        after = len(mem.m.read_events(limit=200))
        assert after > before

    def test_citations_come_only_from_typed_incidents(self, mem, engine):
        mem.upsert_counterparty("rogue", jobs_completed=0, jobs_disputed=1)
        mem.record_incident("rogue", kind="dispute", detail="short-paid the invoice")
        # A decision record mentioning the word "dispute" must not be citable.
        engine.decide("rogue", standard_price_usd=25.0)
        v = engine.decide("rogue", standard_price_usd=25.0)
        assert any("short-paid the invoice" in c for c in v.citations)
        assert all("REFUSED" not in c for c in v.citations)

    def test_verdict_serialises_for_the_wire(self, engine):
        d = engine.decide("someone", standard_price_usd=25.0).to_dict()
        for key in ("decision", "handle", "reason", "quoted_price_usd", "citations"):
            assert key in d
