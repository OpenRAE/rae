"""Semantic joins for authored execution policy using existing language owners."""

from typing import Any

from raes_contracts.execution_policy import ExecutionPolicyScope, resolve_execution_policy

from raes.execution_policy_scope import EXECUTION_SECTIONS, supported_execution_scope
from raes.observation_scope import resolve_observation_scope, semantic_scope_namespace
from raes.orchestration import Workflow


class _ExecutionPolicyMixin:
    def _verify_execution_policy(self) -> None:
        document = self._s.execution_policy
        if document is None:
            return
        payload = self._s.model_dump(mode="python")
        namespaces = {
            tuple(name.split(".")[:-1]) for section in EXECUTION_SECTIONS for name in payload.get(section, {})
        }
        for rule in document.scopes:
            self._verify_policy_scope(rule, payload, namespaces)
        if not self._verify_policy_references():
            return
        for name, workflow in self._s.workflows.items():
            self._verify_workflow_policy(name, workflow, payload)

    def _verify_policy_scope(
        self, rule: ExecutionPolicyScope, payload: dict[str, Any], namespaces: set[tuple[str, ...]]
    ) -> None:
        found, _ = resolve_observation_scope(self._s, rule.scope)
        if not found:
            self._err("Execution policy scope does not resolve to an authored location")
        if not supported_execution_scope(rule.scope):
            self._err("Execution policy scope has no native execution owner")
        if rule.namespace and not any(ns[: len(rule.namespace)] == rule.namespace for ns in namespaces):
            self._err("Execution policy lexical namespace does not resolve")
        if (
            len(rule.scope.split("/")) >= 3
            and rule.namespace
            and semantic_scope_namespace(payload, rule.scope)[: len(rule.namespace)] != rule.namespace
        ):
            self._err("Execution policy scope escapes its lexical namespace")

    def _verify_policy_references(self) -> bool:
        document = self._s.execution_policy
        policies = [rule.policy for rule in document.scopes]
        if document.default is not None:
            policies.append(document.default)
        for policy in policies:
            if policy.clock_ref is not None and policy.clock_ref not in self._s.clocks:
                self._err("Execution policy clock reference does not resolve")
            if any(ref not in self._s.evidence_requirements for ref in policy.evidence_refs):
                self._err("Execution policy evidence reference does not resolve")
                return False
        return True

    def _verify_workflow_policy(self, name: str, workflow: Workflow, payload: dict[str, Any]) -> None:
        scope = "/workflows/" + name
        namespace = semantic_scope_namespace(payload, scope)
        invocation = resolve_execution_policy(
            self._s.execution_policy, scope, namespace=namespace, evidence_requirements=self._s.evidence_requirements
        )
        if (
            invocation is not None
            and invocation.policy.retry.max_attempts > 1
            and any(step.type.value == "retry" and step.max_attempts > 1 for step in workflow.steps.values())
        ):
            self._err("Execution policy cannot multiply native invocation and workflow retry budgets")
        self._verify_workflow_step_policies(workflow, scope, namespace)

    def _verify_workflow_step_policies(self, workflow: Workflow, scope: str, namespace: tuple[str, ...]) -> None:
        for step_name, step in workflow.steps.items():
            effective = resolve_execution_policy(
                self._s.execution_policy,
                scope + "/steps/" + step_name,
                namespace=namespace,
                evidence_requirements=self._s.evidence_requirements,
            )
            if (
                effective is not None
                and "/steps" in effective.governing_scope
                and step.type.value == "retry"
                and effective.policy.retry.max_attempts != step.max_attempts
            ):
                self._err("Execution policy conflicts with the authored workflow retry bound")
