"""Semantic validation adapter for deployment tenancy and placement."""

from ..semantics.deployment_tenancy import analyze_deployment_tenancy


class _DeploymentTenancyMixin:
    def _verify_deployment_tenancy(self) -> None:
        issues = analyze_deployment_tenancy(
            deployment_tenants=self._s.deployment_tenants,
            deployment_cells=self._s.deployment_cells,
            nodes=self._s.nodes,
            persistent_volumes=self._s.persistent_volumes,
            relationships=self._s.relationships,
            is_unresolved=self._is_unresolved_var,
        )
        for issue in issues:
            with self._owner(issue.owner):
                self._err(issue.message)
