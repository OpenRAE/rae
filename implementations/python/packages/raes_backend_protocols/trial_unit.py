"""Single-trial composition protocol for explicitly bound backend adapters."""

from typing import Protocol

from raes_contracts.trial_unit import TrialUnitRequest, TrialUnitResult


class BackendTrialUnit(Protocol):
    """An in-process adapter constructed with an injected RuntimeTarget.

    Implementations compose the shared processor and runtime; they do not
    interpret scenarios or replace backend operation supervision. The caller
    supplies trusted processor outputs and exact admitted identity. The adapter
    reconstructs the request before dispatch, checks its target and capabilities,
    and retains runtime authorization, input/result and evidence validation.
    No method discovery, wire contract or capability declaration is implied.
    """

    def execute_trial(self, request: TrialUnitRequest) -> TrialUnitResult:
        """Execute one entry with its admitted controls and owed cleanup.

        Preserve observations before teardown and report cleanup independently.
        Timeout or interrupted delivery requires existing ledger reconciliation;
        it does not authorize redispatch or prove effects stopped. Resolve
        secret references only at authorized backend sinks. Do not expose raw
        exception text, payloads or backend details. Validate result joins with
        validate_trial_unit_result before handing them to the archival producer.
        """
        ...


__all__ = ["BackendTrialUnit"]
