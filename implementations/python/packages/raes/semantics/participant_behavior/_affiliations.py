"""Affiliation references preserve participant and organization identities."""

from collections.abc import Callable, Collection, Mapping

from ._types import ParticipantBehaviorAnalysis, ParticipantBehaviorIssue, ParticipantBehaviorReference


def analyze_participant_affiliations(
    *,
    agents_by_name: Mapping[str, object],
    entity_names: Collection[str],
    is_unresolved: Callable[[object], bool],
) -> ParticipantBehaviorAnalysis:
    references = []
    issues = []
    for name, participant in agents_by_name.items():
        seen: set[str] = set()
        for affiliation in participant.affiliations:
            if is_unresolved(affiliation):
                continue
            message = None
            if affiliation not in entity_names:
                message = f"Agent '{name}' affiliation references undefined entity '{affiliation}'"
                code = "participant.affiliation-unbound"
            elif affiliation in seen:
                message = f"Agent '{name}' affiliations must name distinct entities"
                code = "participant.affiliation-duplicate"
            if message:
                issues.append(ParticipantBehaviorIssue(code, name, affiliation, message=message))
            else:
                references.append(ParticipantBehaviorReference(name, "affiliation", affiliation, affiliation))
            seen.add(affiliation)
    return ParticipantBehaviorAnalysis(tuple(references), tuple(issues))
