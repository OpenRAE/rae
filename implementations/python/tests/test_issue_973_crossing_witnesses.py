"""Witness admission uses graph bytes, not tool verdicts or mutation names."""

import pytest

LEFT = b'des (0, 1, 2)\n(0,"crossing.decision.deny",1)\n'
RIGHT = b'des (0, 1, 2)\n(0,"internal",1)\n'


def test_formula_is_independently_evaluated_and_canonicalized() -> None:
    from implementations.formal.participant_crossing.counterexample_witnesses import check_formula

    raw = b" <tau*> <crossing.decision.deny> true \n"
    assert check_formula(LEFT, RIGHT, raw) == b"<tau*><crossing.decision.deny>true\n"
    with pytest.raises(ValueError, match="formula does not distinguish"):
        check_formula(RIGHT, LEFT, raw)
    with pytest.raises(ValueError, match="formula does not distinguish"):
        check_formula(LEFT, LEFT, raw)


@pytest.mark.parametrize(
    "raw",
    [
        b"<payload.secret>true",
        b"/home/user/file",
        b"<tau*>true\ncommand()",
        b"(" * 80 + b"true" + b")" * 80,
        b"true" * 20000,
        b"<tau*>nu X.X",
        b"<tau*>true\x00",
    ],
    ids=("payload", "host-path", "trailing-command", "depth", "size", "fixpoint", "nul"),
)
def test_unsafe_or_unbounded_formulas_are_refused(raw: bytes) -> None:
    from implementations.formal.participant_crossing.counterexample_witnesses import check_formula

    with pytest.raises(ValueError):
        check_formula(LEFT, RIGHT, raw)


def test_boolean_boxes_and_tau_closure_have_modal_semantics() -> None:
    from implementations.formal.participant_crossing.counterexample_witnesses import check_formula

    assert check_formula(RIGHT, LEFT, b"[tau*][crossing.decision.deny]false")
    assert check_formula(LEFT, RIGHT, b"!([tau*][crossing.decision.deny]false) && true")


def test_divergence_checks_reachable_prefix_and_nonempty_cycle() -> None:
    from implementations.formal.participant_crossing.counterexample_witnesses import check_divergence

    abstract = b'des (0, 1, 2)\n(0,"crossing.request",1)\n'
    divergent = b'des (0, 2, 2)\n(0,"crossing.request",1)\n(1,"internal",1)\n'
    witness = {"prefix": [[0, "crossing.request", 1]], "cycle": [[1, "internal", 1]]}
    check_divergence(abstract, divergent, witness)
    for invalid in (
        {"prefix": [], "cycle": [[1, "internal", 1]]},
        {"prefix": witness["prefix"], "cycle": []},
        {"prefix": [[False, "crossing.request", 1]], "cycle": witness["cycle"]},
    ):
        with pytest.raises(ValueError):
            check_divergence(abstract, divergent, invalid)
    with pytest.raises(ValueError):
        check_divergence(abstract, abstract, witness)
    with pytest.raises(ValueError):
        check_divergence(divergent, divergent, witness)


def test_unreachable_cycle_cannot_supply_divergence_evidence() -> None:
    from implementations.formal.participant_crossing.counterexample_witnesses import check_divergence

    with pytest.raises(ValueError):
        check_divergence(
            b"des (0, 0, 1)\n", b'des (0, 1, 2)\n(1,"internal",1)\n', {"prefix": [], "cycle": [[1, "internal", 1]]}
        )
