"""Portable shape constraints for explicit partial run records."""

from typing import Any


def add_record_shape_schema(schema: dict[str, Any]) -> None:
    from .schema_invariants import _add_raes_invariant

    _add_raes_invariant(
        schema,
        "run-execution-accounting-consistent",
        "Execution accounting preserves unique ordered attempts, run-bound evidence and cleanup, "
        "exact start and bounded end times, and status consistent with the observed lifecycle. "
        "Archival accounting agrees with admitted trial provenance identities, attempts, "
        "operation references and cleanup membership.",
        inputs=[{"contract_id": "experiment-run-v1", "instance_path": "#"}],
    )
    schema.setdefault("allOf", []).append(
        {
            "if": {"properties": {"record_state": {"const": "partial"}}, "required": ["record_state"]},
            "then": {
                "required": ["execution_accounting"],
                "properties": {
                    "execution_accounting": {"type": "object"},
                    "outcome_status": {"not": {"const": "succeeded"}},
                    "run_status": {"not": {"const": "sealed"}},
                },
            },
            "else": {
                "allOf": [
                    {
                        "if": {
                            "properties": {"execution_accounting": {"type": "object"}},
                            "required": ["execution_accounting"],
                        },
                        "then": {
                            "required": ["trial_provenance"],
                            "properties": {"trial_provenance": {"type": "object"}},
                        },
                    }
                ],
                "required": [
                    "ended_at",
                    "apparatus_context",
                    "traceability",
                    "parameter_set",
                    "stochastic_controls",
                    "evidence_artifacts",
                    "result_summaries",
                ],
                "properties": {
                    "ended_at": {"type": "string"},
                    "apparatus_context": {"type": "object"},
                    "traceability": {"type": "object"},
                    "evidence_artifacts": {"minItems": 1},
                    "result_summaries": {"minProperties": 1},
                    "run_status": {"not": {"enum": ["in-progress", "indeterminate"]}},
                },
            },
        }
    )
    schema.setdefault("allOf", []).append(
        {
            "if": {
                "properties": {"run_status": {"enum": ["in-progress", "indeterminate"]}},
                "required": ["run_status"],
            },
            "then": {"properties": {"ended_at": {"type": "null"}}},
        }
    )

    schema.setdefault("allOf", []).append(
        {
            "if": {"not": {"required": ["execution_accounting"]}},
            "then": {
                "if": {"not": {"properties": {"record_state": {"const": "partial"}}, "required": ["record_state"]}},
                "then": {"properties": {"parameter_set": {"minItems": 1}, "stochastic_controls": {"minItems": 1}}},
            },
        }
    )
