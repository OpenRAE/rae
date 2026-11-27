"""Participant tool-affordance identity validation (SEM-219)."""


class _ParticipantToolAffordancesMixin:
    def _verify_tool_affordance_tool_refs(self) -> None:
        if self._declaration_index is None:
            raise RuntimeError("declaration index must be built before reference validation")
        for spec_name, behavior_spec in self._s.behavior_specifications.items():
            for affordance_id, binding in behavior_spec.tool_affordances.items():
                with self._owner(("behavior_specifications", spec_name)):
                    self._verify_tool_affordance_tool_ref(spec_name, affordance_id, binding.tool_ref)

    def _verify_tool_affordance_tool_ref(self, spec_name: str, affordance_id: str, tool_ref: object) -> None:
        if tool_ref is None or self._is_unresolved_var(tool_ref):
            return
        if self._declaration_index is None:
            raise RuntimeError("declaration index must be built before reference validation")
        all_candidates = self._declaration_index.resolve(tool_ref)
        label = f"Behavior specification '{spec_name}' tool affordance '{affordance_id}'"
        if not all_candidates:
            self._err(f"{label} tool_ref '{tool_ref}' does not reference a declared scenario content identity")
            return
        if len(all_candidates) > 1:
            choices = ", ".join(sorted(all_candidates))
            self._err(f"{label} tool_ref '{tool_ref}' is ambiguous; use one of: {choices}")
            return
        candidate = next(iter(all_candidates))
        declaration = self._declaration_index.declaration_for(candidate)
        if declaration is None or declaration.kind != "content":
            self._err(
                f"{label} tool_ref '{tool_ref}' must resolve through the scenario-content "
                "tools-and-artifacts reference model"
            )
