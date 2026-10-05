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
    if tokens[0] not in EXECUTION_SECTIONS:
        return False
    if len(tokens) <= 2:
        return True
    if tokens[0] == "workflows" and tokens[2] == "steps":
        return len(tokens) <= 4
    return tokens[0] == "nodes" and len(tokens) <= 4 and tokens[2] in {"features", "conditions", "injects"}
