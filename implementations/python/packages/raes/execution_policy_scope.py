"""The authored locations with native execution-policy owners."""

EXECUTION_SECTIONS = frozenset(
    {
        "nodes",
        "features",
        "conditions",
        "injects",
        "identity_domains",
        "accounts",
        "content",
        "generated_artifacts",
        "persistent_volumes",
        "events",
        "scripts",
        "stories",
        "workflows",
        "propositions",
        "assertions",
        "objectives",
    }
)


def supported_execution_scope(pointer: str) -> bool:
    if not pointer:
        return True
    tokens = pointer.split("/")[1:]
    nested = len(tokens) > 2 and (
        (tokens[0] == "workflows" and tokens[2] == "steps")
        or (tokens[0] == "nodes" and tokens[2] in {"features", "conditions", "injects"})
    )
    return tokens[0] in EXECUTION_SECTIONS and (len(tokens) <= 2 or (nested and len(tokens) <= 4))
