"""Participant-local interactive-access semantic analysis (DSL-117)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from raes_contracts.domain_profiles import DomainProfileBindingModel

from ._domain_topology_types import resolve_section_ref


@dataclass(frozen=True)
class ParticipantInteractiveAccessIssue:
    """One fail-closed authored interactive-access invariant violation."""

    code: str
    message: str


@dataclass(frozen=True)
class _ParticipantAccountContext:
    """Participant-local inputs shared by account-binding checks."""

    nodes: Mapping[str, object]
    accounts: Mapping[str, object]
    starting_accounts: frozenset[str]
    unresolved_starting_ref: bool
    is_unresolved: Callable[[object], bool]


def _concrete_channel(value: object, *, is_unresolved: Callable[[object], bool]) -> str | None:
    if is_unresolved(value):
        return None
    if isinstance(value, DomainProfileBindingModel):
        return value.coordinate.model_dump_json()
    channel = getattr(value, "value", value)
    return channel if isinstance(channel, str) else None


def _starting_account_context(
    agent: object,
    *,
    accounts: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> tuple[set[str], bool]:
    """Resolve concrete starting-account authority for one participant."""

    starting_refs = tuple(getattr(agent, "starting_accounts", ()))
    concrete: set[str] = set()
    for ref in starting_refs:
        if is_unresolved(ref):
            continue
        resolved = resolve_section_ref(ref, "accounts", accounts)
        if resolved is not None:
            concrete.add(resolved)
    return concrete, any(is_unresolved(ref) for ref in starting_refs)


def _analyze_target(
    *,
    label: str,
    target_ref: object,
    nodes: Mapping[str, object],
    is_vm_node: Callable[[str], bool],
    is_unresolved: Callable[[object], bool],
) -> tuple[str | None, tuple[ParticipantInteractiveAccessIssue, ...]]:
    """Resolve one target and return any target-local issue."""

    if is_unresolved(target_ref):
        return None, ()
    target_name = resolve_section_ref(target_ref, "nodes", nodes)
    issue: ParticipantInteractiveAccessIssue | None = None
    if target_name is None:
        issue = ParticipantInteractiveAccessIssue(
            code="participant.interactive-access-target-unbound",
            message=f"{label} target_ref '{target_ref}' does not reference a declared compute node",
        )
    elif not is_vm_node(target_name):
        issue = ParticipantInteractiveAccessIssue(
            code="participant.interactive-access-target-not-vm",
            message=f"{label} target_ref '{target_ref}' must reference a compute node",
        )
    return target_name, () if issue is None else (issue,)


def _resolved_account_node(
    account: object,
    *,
    nodes: Mapping[str, object],
    is_unresolved: Callable[[object], bool],
) -> str | None:
    account_node_ref = getattr(account, "node", "")
    if is_unresolved(account_node_ref):
        return None
    return resolve_section_ref(account_node_ref, "nodes", nodes)


def _analyze_account(
    *,
    label: str,
    access: object,
    target_name: str | None,
    context: _ParticipantAccountContext,
) -> tuple[ParticipantInteractiveAccessIssue, ...]:
    """Evaluate optional account resolution and participant authority."""

    issues: list[ParticipantInteractiveAccessIssue] = []
    account_ref = getattr(access, "account_ref", None)
    if account_ref is None or context.is_unresolved(account_ref):
        return tuple(issues)

    account_name = resolve_section_ref(account_ref, "accounts", context.accounts)
    if account_name is None:
        issues.append(
            ParticipantInteractiveAccessIssue(
                code="participant.interactive-access-account-unbound",
                message=f"{label} account_ref '{account_ref}' does not reference a declared account",
            )
        )
        return tuple(issues)

    account_node = _resolved_account_node(
        context.accounts[account_name],
        nodes=context.nodes,
        is_unresolved=context.is_unresolved,
    )
    if target_name is not None and account_node is not None and account_node != target_name:
        issues.append(
            ParticipantInteractiveAccessIssue(
                code="participant.interactive-access-account-node-mismatch",
                message=(
                    f"{label} account_ref '{account_ref}' belongs to node '{account_node}', not target '{target_name}'"
                ),
            )
        )
    if account_name not in context.starting_accounts and not context.unresolved_starting_ref:
        issues.append(
            ParticipantInteractiveAccessIssue(
                code="participant.interactive-access-account-not-starting",
                message=f"{label} account_ref '{account_ref}' is not in starting_accounts",
            )
        )
    return tuple(issues)


def _duplicate_endpoint_issue(
    *,
    label: str,
    access_id: str,
    target_name: str | None,
    channel: str | None,
    seen_endpoints: dict[tuple[str, str], str],
    is_vm_node: Callable[[str], bool],
) -> ParticipantInteractiveAccessIssue | None:
    """Record one canonical endpoint, or describe its duplicate."""

    if target_name is None or channel is None or not is_vm_node(target_name):
        return None
    endpoint_key = (target_name, channel)
    first_access_id = seen_endpoints.get(endpoint_key)
    if first_access_id is None:
        seen_endpoints[endpoint_key] = access_id
        return None
    return ParticipantInteractiveAccessIssue(
        code="participant.interactive-access-duplicate-endpoint",
        message=(
            f"{label} duplicates interactive_access target/channel "
            f"'{target_name}'/'{channel}' declared by '{first_access_id}'"
        ),
    )


def analyze_participant_interactive_access(
    *,
    agents_by_name: Mapping[str, object],
    nodes: Mapping[str, object],
    accounts: Mapping[str, object],
    is_vm_node: Callable[[str], bool],
    is_unresolved: Callable[[object], bool],
) -> tuple[ParticipantInteractiveAccessIssue, ...]:
    """Evaluate resolution, authority, and uniqueness for every participant."""

    issues: list[ParticipantInteractiveAccessIssue] = []
    for participant_name, agent in agents_by_name.items():
        seen_endpoints: dict[tuple[str, str], str] = {}
        starting_accounts, unresolved_starting_ref = _starting_account_context(
            agent,
            accounts=accounts,
            is_unresolved=is_unresolved,
        )
        account_context = _ParticipantAccountContext(
            nodes=nodes,
            accounts=accounts,
            starting_accounts=frozenset(starting_accounts),
            unresolved_starting_ref=unresolved_starting_ref,
            is_unresolved=is_unresolved,
        )
        for access_id, access in getattr(agent, "interactive_access", {}).items():
            label = f"Agent '{participant_name}' interactive_access '{access_id}'"
            target_name, target_issues = _analyze_target(
                label=label,
                target_ref=getattr(access, "target_ref", ""),
                nodes=nodes,
                is_vm_node=is_vm_node,
                is_unresolved=is_unresolved,
            )
            issues.extend(target_issues)
            issues.extend(
                _analyze_account(
                    label=label,
                    access=access,
                    target_name=target_name,
                    context=account_context,
                )
            )
            channel = _concrete_channel(getattr(access, "channel", None), is_unresolved=is_unresolved)
            duplicate_issue = _duplicate_endpoint_issue(
                label=label,
                access_id=access_id,
                target_name=target_name,
                channel=channel,
                seen_endpoints=seen_endpoints,
                is_vm_node=is_vm_node,
            )
            if duplicate_issue is not None:
                issues.append(duplicate_issue)
    return tuple(issues)


__all__ = ["ParticipantInteractiveAccessIssue", "analyze_participant_interactive_access"]
