"""Semantic validation adapter for authored identity-domain topology."""

from ..semantics.domain_topology import analyze_domain_topology


class _DomainTopologyMixin:
    def _verify_domain_topology(self) -> None:
        analysis = analyze_domain_topology(
            identity_domains=self._s.identity_domains,
            nodes=self._s.nodes,
            accounts=self._s.accounts,
            relationships=self._s.relationships,
            is_unresolved=self._is_unresolved_var,
        )
        for issue in analysis.issues:
            with self._owner(issue.owner):
                self._err(issue.message)
