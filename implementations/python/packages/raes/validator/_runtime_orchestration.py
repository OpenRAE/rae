"""SemanticValidator _RuntimeOrchestrationMixin (split from _runtime_platform.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""


class _RuntimeOrchestrationMixin:
    def _verify_runtime_orchestration_authorities(self) -> None:
        """Validate observed container-spawn orchestration-authority inventories.

        Each authority's ``control_interface_ref``, when present and concrete,
        must resolve to a :class:`RuntimeControlInterface` declared in the same
        node's ``runtime.local_control_interfaces`` (by ``control_interface_id``).
        Description validity does not establish effective privilege. Selected
        execution admission owns mechanism, access and completeness checks.
        """
        for node_name, node in self._s.nodes.items():
            runtime = getattr(node, "runtime", None)
            if runtime is None or not runtime.orchestration_authorities:
                continue
            interfaces_by_id = {
                interface.control_interface_id: interface
                for interface in getattr(runtime, "local_control_interfaces", [])
                if interface.control_interface_id
            }
            for authority in runtime.orchestration_authorities:
                self._verify_orchestration_authority(
                    node_name=node_name,
                    authority=authority,
                    interfaces_by_id=interfaces_by_id,
                )

    def _verify_orchestration_authority(
        self,
        *,
        node_name: str,
        authority: object,
        interfaces_by_id: dict[str, object],
    ) -> None:
        owner_label = f"Node '{node_name}' runtime orchestration authority '{authority.orchestration_authority_id}'"
        ref = getattr(authority, "control_interface_ref", "")
        if not ref or self._is_unresolved_var(ref):
            return
        interface = interfaces_by_id.get(ref)
        if interface is None:
            self._err(
                f"{owner_label} control_interface_ref '{ref}' does not resolve to a "
                f"control interface in the same node's runtime.local_control_interfaces"
            )
