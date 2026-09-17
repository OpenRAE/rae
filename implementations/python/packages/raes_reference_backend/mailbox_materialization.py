"""Protected in-process mailbox authentication sink for the portable reference."""

from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy
from dataclasses import dataclass, field

from raes_contracts.account_materialization import AccountMailboxMaterialization, account_mailbox_materializations
from raes_contracts.diagnostics import Diagnostic
from raes_contracts.planning import ChangeAction, ProvisioningPlan


@dataclass
class InProcessMailboxSink:
    """Explicit backend authorization and private emulated authentication state.

    This is backend realization state, not another authored credential registry.
    Operator references are retained as references and are never resolved.
    """

    authorized_bindings: frozenset[tuple[str, str]]
    _verifiers: dict[str, bytes] = field(default_factory=dict, init=False, repr=False)
    _operator_references: dict[str, tuple[str, ...]] = field(default_factory=dict, init=False, repr=False)
    _mailboxes: dict[str, dict[str, object]] = field(default_factory=dict, init=False, repr=False)
    _owners: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def permits(self, request: AccountMailboxMaterialization) -> bool:
        return (request.account_address, request.mailbox_ref) in self.authorized_bindings

    def materialize(self, requests: tuple[AccountMailboxMaterialization, ...]) -> None:
        if any(not self.permits(request) for request in requests):
            raise ValueError("Mailbox sink authorization denied")
        changed = {request.account_address for request in requests}
        for reference, owner in tuple(self._owners.items()):
            if owner in changed:
                self._remove(reference)
        for request in requests:
            self._verifiers[request.mailbox_ref] = hashlib.sha256(request.fixture.encode("utf-8")).digest()
            self._operator_references[request.mailbox_ref] = request.operator_references
            self._mailboxes[request.mailbox_ref] = deepcopy(dict(request.mailbox))
            self._owners[request.mailbox_ref] = request.account_address

    def remove_deleted(self, plan: ProvisioningPlan) -> None:
        deleted = {
            op.address
            for op in plan.operations
            if op.action is ChangeAction.DELETE
            or (
                op.resource_type == "account-placement"
                and not any(binding.owner.context == "account-materialization" for binding in op.profile_bindings)
            )
        }
        for reference, owner in tuple(self._owners.items()):
            if owner in deleted:
                self._remove(reference)

    def _remove(self, reference: str) -> None:
        self._owners.pop(reference)
        self._verifiers.pop(reference, None)
        self._operator_references.pop(reference, None)
        self._mailboxes.pop(reference, None)

    def authenticates(self, mailbox_ref: str, candidate: str) -> bool:
        verifier = self._verifiers.get(mailbox_ref)
        return verifier is not None and hmac.compare_digest(
            verifier, hashlib.sha256(candidate.encode("utf-8")).digest()
        )


def mailbox_sink_diagnostics(plan: ProvisioningPlan, sink: InProcessMailboxSink | None) -> list[Diagnostic]:
    """Refuse unsupported joins and unauthorized sinks before any driver mutation."""

    try:
        requests = account_mailbox_materializations(plan)
        if requests and (
            not isinstance(sink, InProcessMailboxSink) or any(not sink.permits(item) for item in requests)
        ):
            raise ValueError("No authorized protected mailbox sink")
    except (AttributeError, KeyError, TypeError, ValueError):
        return [
            Diagnostic(
                "reference-backend.mailbox-unsupported",
                "provisioning",
                "accounts",
                "Account/mailbox materialization is unsupported.",
            )
        ]
    return []
