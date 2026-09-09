"""SemanticValidator _SectionsMixin (split from validator.py).

Part of the SemanticValidator mixin composition; see __init__.py.
"""

from pydantic import BaseModel

from .._base import VARIABLE_TOKEN_RE
from .._stateful_resource_references import stateful_resource_reference_errors
from ..entities import flatten_entities
from ..explicitness import classify_scenario_explicitness
from ..nodes import Node, NodeType
from ..realization_designation import (
    RealizationConstraintRecord,
    RealizationDesignationRecord,
    designation_records,
    resolve_json_pointer_surface,
)
from ..scenario import ExpandedScenario, Scenario
from ._support import _topological_sort


class _SectionsMixin:
    def _verify_stateful_resources(self) -> None:
        self._errors.extend(
            stateful_resource_reference_errors(
                nodes=self._s.nodes,
                generated_artifacts=self._s.generated_artifacts,
                persistent_volumes=self._s.persistent_volumes,
            )
        )

    def _verify_variables(self) -> None:
        defined = set(getattr(self._s, "variables", {}))
        self._check_variable_refs(self._s, "", defined)

    def _check_variable_refs(self, value: object, path: str, defined: set[str]) -> None:
        if isinstance(value, BaseModel):
            self._check_model_variable_refs(value, path, defined)
            return
        if isinstance(value, dict):
            self._check_mapping_variable_refs(value, path, defined)
            return
        if isinstance(value, list):
            self._check_sequence_variable_refs(value, path, defined)
            return
        if isinstance(value, str):
            self._check_string_variable_refs(value, path, defined)

    def _check_model_variable_refs(self, value: BaseModel, path: str, defined: set[str]) -> None:
        for field_name in value.__class__.model_fields:
            if isinstance(value, Scenario) and field_name == "variables":
                continue
            child = getattr(value, field_name)
            child_path = f"{path}.{field_name}" if path else field_name
            self._check_variable_refs(child, child_path, defined)

    def _check_mapping_variable_refs(self, value: dict[object, object], path: str, defined: set[str]) -> None:
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            self._check_variable_refs(child, child_path, defined)

    def _check_sequence_variable_refs(self, value: list[object], path: str, defined: set[str]) -> None:
        for index, child in enumerate(value):
            self._check_variable_refs(child, f"{path}[{index}]", defined)

    def _check_string_variable_refs(self, value: str, path: str, defined: set[str]) -> None:
        for variable_name in dict.fromkeys(VARIABLE_TOKEN_RE.findall(value)):
            if variable_name not in defined:
                self._err(f"Undefined variable '{variable_name}' referenced at '{path}'")

    def _verify_explicitness(self) -> None:
        result = classify_scenario_explicitness(self._s)
        self._s._set_explicitness(result.records)
        for error in result.errors:
            self._err(error)

    def _verify_realization_designations(self) -> None:
        records, constraints, known_namespaces = self._realization_designation_surfaces()
        for record in records:
            self._verify_realization_designation_record(record, known_namespaces)
        for constraint in constraints:
            self._verify_realization_constraint_record(constraint, known_namespaces)

    def _realization_designation_surfaces(
        self,
    ) -> tuple[
        tuple[RealizationDesignationRecord, ...],
        tuple[RealizationConstraintRecord, ...],
        set[tuple[str, ...]],
    ]:
        known_namespaces: set[tuple[str, ...]] = {()}
        if isinstance(self._s, Scenario) and self._s.realization is not None:
            records = designation_records(self._s.realization)
            constraints = self._s.realization.constraints
        elif isinstance(self._s, ExpandedScenario):
            records = self._s.expansion_provenance.realization_designations
            constraints = self._s.expansion_provenance.realization_constraints
            known_namespaces.update(record.namespace for record in self._s.expansion_provenance.imports)
        else:
            records = ()
            constraints = ()
        return tuple(records), tuple(constraints), known_namespaces

    def _verify_realization_designation_record(
        self,
        record: RealizationDesignationRecord,
        known_namespaces: set[tuple[str, ...]],
    ) -> None:
        if record.namespace not in known_namespaces:
            self._err("Realization designation references an unresolved module namespace")
        found, _value = resolve_json_pointer_surface(self._s, record.field_pointer)
        if not found:
            self._err(
                "Realization designation field_pointer does not resolve to a typed SDL surface: "
                f"{record.field_pointer or '/'}"
            )

    def _verify_realization_constraint_record(
        self,
        constraint: RealizationConstraintRecord,
        known_namespaces: set[tuple[str, ...]],
    ) -> None:
        if constraint.namespace not in known_namespaces:
            self._err("Realization constraint references an unresolved module namespace")
            return
        found, target = resolve_json_pointer_surface(self._s, constraint.field_pointer)
        if not found or not isinstance(target, Node):
            self._err(
                f"Realization constraint field_pointer must resolve to a compute node: {constraint.field_pointer}"
            )
        elif target.type is NodeType.SWITCH:
            self._err(
                f"Realization concern '{constraint.concern.value}' cannot target strict switch "
                f"'{constraint.field_pointer}'"
            )

    def _all_named_elements(self) -> set[str]:
        """Collect all named element keys across all scenario sections."""
        return set(self._named_ref_index().keys())

    def _all_targetable_elements(self) -> set[str]:
        """Collect named elements that can serve as objective targets."""
        return set(self._named_ref_index(targetable=True).keys())

    def _verify_features(self) -> None:
        self._verify_feature_dependency_cycles()

    def _verify_feature_dependency_cycles(self) -> None:
        dep_graph: dict[str, list[str]] = {}
        for name, feat in self._s.features.items():
            dep_graph[name] = []
            for dep in feat.dependencies:
                if self._is_unresolved_var(dep):
                    continue
                if dep not in self._s.features:
                    self._err(f"Feature '{name}' depends on undefined feature '{dep}'")
                else:
                    dep_graph[name].append(dep)
        if dep_graph and _topological_sort(dep_graph) is None:
            self._err("Feature dependency graph contains a cycle")

    def _verify_conditions(self) -> None:
        # Individual condition validation is handled by Pydantic model_validator.
        # This pass checks for consistency with the broader scenario.
        pass

    def _verify_entities(self) -> None:
        for name, entity in flatten_entities(self._s.entities).items():
            self._verify_entity_refs(name, entity)

    def _verify_entity_refs(self, name: str, entity: object) -> None:
        self._verify_membership_refs(
            entity.events, self._s.events, lambda ref: f"Entity '{name}' references undefined event '{ref}'"
        )

    def _verify_injects(self) -> None:
        flat_names = self._all_entity_names()
        for name, inject in self._s.injects.items():
            self._verify_inject_refs(name, inject, flat_names)

    def _verify_inject_refs(self, name: str, inject: object, flat_names: set[str]) -> None:
        if (
            inject.from_entity
            and not self._is_unresolved_var(inject.from_entity)
            and inject.from_entity not in flat_names
        ):
            self._err(f"Inject '{name}' from_entity '{inject.from_entity}' is not a defined entity")
        self._verify_membership_refs(
            inject.to_entities, flat_names, lambda ref: f"Inject '{name}' to_entity '{ref}' is not a defined entity"
        )

    def _verify_events(self) -> None:
        for name, event in self._s.events.items():
            self._verify_event_refs(name, event)

    def _verify_event_refs(self, name: str, event: object) -> None:
        self._verify_membership_refs(
            event.injects, self._s.injects, lambda ref: f"Event '{name}' references undefined inject '{ref}'"
        )

    def _verify_scripts(self) -> None:
        for name, script in self._s.scripts.items():
            for event_name in script.events:
                if self._is_unresolved_var(event_name):
                    continue
                if event_name not in self._s.events:
                    self._err(f"Script '{name}' references undefined event '{event_name}'")

    def _verify_stories(self) -> None:
        for name, story in self._s.stories.items():
            for script_name in story.scripts:
                if self._is_unresolved_var(script_name):
                    continue
                if script_name not in self._s.scripts:
                    self._err(f"Story '{name}' references undefined script '{script_name}'")

    def _verify_roles(self) -> None:
        flat_names = self._all_entity_names()

        for node_name, node in self._s.nodes.items():
            for role_name, role in node.roles.items():
                for entity_ref in role.entities:
                    if self._is_unresolved_var(entity_ref):
                        continue
                    if entity_ref not in flat_names:
                        self._err(f"Node '{node_name}' role '{role_name}' references undefined entity '{entity_ref}'")
