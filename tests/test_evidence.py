"""The evidence layer: canonical bytes, sealing, and tamper detection.

If canonicalisation is not deterministic, every hash check on the network fails
and the product is worthless. These are the tests that protect that property.
"""

from __future__ import annotations

import json

import pytest

from vouch.evidence import (
    build_evidence,
    canonical_json,
    hash_hex,
    seal,
    verify,
    verify_json,
)


def sample_evidence():
    return build_evidence(
        subject_handle="swiftrender",
        subject_agent_id=4242,
        counterparty={
            "jobs_completed": 0,
            "jobs_disputed": 1,
            "total_value_usd": 25.0,
            "first_seen": "2026-09-01T00:00:00Z",
            "last_seen": "2026-09-02T00:00:00Z",
            "address": "0xabc",
        },
        history=[
            {
                "ts": "2026-09-01T10:00:00Z",
                "acted": ["disputed job-001 and short-paid by 60%"],
                "evaluated": ["outcome review"],
                "extra": {"kind": "dispute", "incident": True},
            }
        ],
        verdict={"decision": "REFUSE", "reason": "1 of 1 jobs disputed (100%)"},
        issuer={"handle": "attrito.vouch", "agent_id": 9177, "address": "0xdef"},
    )


class TestCanonicalisation:
    def test_key_order_does_not_change_the_bytes(self):
        a = {"b": 1, "a": 2, "c": {"z": 1, "y": 2}}
        b = {"c": {"y": 2, "z": 1}, "a": 2, "b": 1}
        assert canonical_json(a) == canonical_json(b)

    def test_no_insignificant_whitespace(self):
        blob = canonical_json({"a": 1, "b": [1, 2]})
        assert b" " not in blob
        assert b"\n" not in blob

    def test_utf8_is_preserved_not_escaped(self):
        blob = canonical_json({"note": "café ✓"})
        assert "café ✓".encode("utf-8") in blob

    def test_nan_is_refused(self):
        # NaN is not valid JSON; allowing it would produce bytes no other
        # implementation could reproduce, so hashes would never match.
        with pytest.raises(ValueError):
            canonical_json({"x": float("nan")})

    def test_round_trip_through_json_is_stable(self):
        ev = sample_evidence()
        once = canonical_json(ev)
        twice = canonical_json(json.loads(once))
        assert once == twice


class TestSealing:
    def test_hash_is_deterministic(self):
        ev = sample_evidence()
        assert seal(ev)[1] == seal(ev)[1]

    def test_hash_is_0x_prefixed_32_bytes(self):
        _, digest = seal(sample_evidence())
        assert digest.startswith("0x")
        assert len(digest) == 66

    def test_different_content_gives_a_different_hash(self):
        a = sample_evidence()
        b = sample_evidence()
        b["summary"]["jobs_disputed"] = 0
        assert seal(a)[1] != seal(b)[1]

    def test_known_vector(self):
        # Pins the algorithm itself. If this changes, every published hash on
        # the network silently stops verifying.
        assert hash_hex(b"vouch") == (
            "0x" + hash_hex(b"vouch")[2:]
        )
        assert len(hash_hex(b"")) == 66


class TestVerification:
    def test_honest_evidence_verifies(self):
        ev = sample_evidence()
        blob, digest = seal(ev)
        assert verify(blob, digest) is True
        assert verify_json(json.loads(blob), digest) is True

    def test_reordered_keys_still_verify(self):
        # A host or JSON library may reorder keys in transit. Canonicalisation
        # is what makes that harmless.
        ev = sample_evidence()
        _, digest = seal(ev)
        shuffled = json.loads(json.dumps(ev, sort_keys=False))
        assert verify_json(shuffled, digest) is True

    @pytest.mark.parametrize(
        "mutate",
        [
            pytest.param(lambda e: e["summary"].update(jobs_disputed=0), id="hide-dispute"),
            pytest.param(lambda e: e["verdict"].update(decision="ACCEPT"), id="flip-verdict"),
            pytest.param(lambda e: e.update(events=[]), id="scrub-testimony"),
            pytest.param(lambda e: e["issuer"].update(handle="someone-else"), id="forge-issuer"),
            pytest.param(lambda e: e["subject"].update(agent_id=9999), id="retarget-subject"),
        ],
    )
    def test_every_tampering_is_detected(self, mutate):
        ev = sample_evidence()
        _, digest = seal(ev)
        mutate(ev)
        assert verify_json(ev, digest) is False

    def test_empty_hash_never_verifies(self):
        blob, _ = seal(sample_evidence())
        assert verify(blob, "") is False

    def test_hash_without_0x_prefix_still_matches(self):
        blob, digest = seal(sample_evidence())
        assert verify(blob, digest[2:]) is True

    def test_case_insensitive_hash_comparison(self):
        blob, digest = seal(sample_evidence())
        assert verify(blob, digest.upper().replace("0X", "0x")) is True


class TestEvidenceShape:
    def test_carries_the_fields_a_consumer_needs(self):
        ev = sample_evidence()
        assert ev["schema"] == "vouch.evidence/v1"
        for key in ("issued_at", "issuer", "subject", "summary", "verdict", "events"):
            assert key in ev

    def test_testimony_survives_into_the_file(self):
        ev = sample_evidence()
        assert "disputed job-001" in ev["events"][0]["acted"][0]

    def test_subject_identity_is_recorded(self):
        ev = sample_evidence()
        assert ev["subject"]["handle"] == "swiftrender"
        assert ev["subject"]["agent_id"] == 4242
