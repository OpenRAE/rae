"""Semantic validation adapter for enterprise identity intent."""

from ..semantics.enterprise_identity import analyze_enterprise_identity


class _EnterpriseIdentityMixin:
    def _verify_enterprise_identity(self) -> None:
        issues = analyze_enterprise_identity(
            identity_domains=self._s.identity_domains,
            identity_forests=self._s.identity_forests,
            identity_facades=self._s.identity_facades,
            nodes=self._s.nodes,
            relationships=self._s.relationships,
            is_unresolved=self._is_unresolved_var,
        )
        for issue in issues:
            with self._owner(issue.owner):
                self._err(issue.message)
