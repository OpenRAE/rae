"""Account semantic checks for the SDL validator."""

from ..accounts import account_credential_binding_issues


class _AccountsMixin:
    def _verify_accounts(self) -> None:
        for name, account in self._s.accounts.items():
            with self._owner(("accounts", name)):
                if account.node and not self._is_unresolved_var(account.node) and account.node not in self._s.nodes:
                    self._err(f"Account '{name}' references undefined node '{account.node}'")
                elif (
                    account.node
                    and not self._is_unresolved_var(account.node)
                    and not self._is_compute_node(account.node)
                ):
                    self._err(f"Account '{name}' node '{account.node}' must be a compute node")
                for issue in account_credential_binding_issues(account):
                    self._err(f"Account '{name}' {issue}")
