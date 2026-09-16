"""Semantic admission of common SDL content before a producer materializes it."""

from typing import ClassVar

from ._scenario_instantiation import collect_variable_tokens
from .scenario import ScenarioContent


class ProspectiveScenarioContent(ScenarioContent):
    """Internal validation view: no new SDL document phase or execution authority."""

    _allows_qualified_declaration_keys: ClassVar[bool] = True


def admit_prospective_content(payload: dict[str, object]) -> ScenarioContent:
    from .validator import SemanticValidator

    if collect_variable_tokens(payload):
        raise ValueError("prospective SDL cannot contain unresolved variables")
    admitted = ProspectiveScenarioContent.model_validate(payload)
    SemanticValidator(admitted).validate()
    return admitted
