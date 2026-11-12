"""Semantic validation for portable runtime process-resource limits."""

from ..runtime_resource_limits import process_resource_limit_subject_matches


class _RuntimeProcessLimitsMixin:
    def _verify_runtime_process_resource_limits(self) -> None:
        """Cross-check the complete normalized selector against process inventory."""

        for node_name, node in self._s.nodes.items():
            limits = self._process_resource_limits_for(node)
            if not limits:
                continue
            runtime = getattr(node, "runtime", None)
            processes = list(getattr(runtime, "processes", None) or [])
            for process_limit in limits:
                if not any(
                    process_resource_limit_subject_matches(process_limit.subject, process) for process in processes
                ):
                    with self._owner(("nodes", node_name)):
                        self._err(
                            f"Node '{node_name}' runtime process resource limit subject does not match any process "
                            "declared in 'runtime.processes'"
                        )

    @staticmethod
    def _process_resource_limits_for(node: object) -> list[object]:
        runtime = getattr(node, "runtime", None)
        policy = getattr(runtime, "operational_policy", None) if runtime is not None else None
        resource_limits = getattr(policy, "resource_limits", None) if policy is not None else None
        return list(getattr(resource_limits, "process_limits", None) or [])
