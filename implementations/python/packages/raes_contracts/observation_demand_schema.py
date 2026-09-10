"""Published effective-demand invariants shared by every plan schema."""

from pydantic.json_schema import JsonSchemaValue


def effective_observation_schema(schema: JsonSchemaValue) -> JsonSchemaValue:
    stages = ("collection", "retention", "export")
    schema.setdefault("allOf", []).extend(
        [
            {
                "properties": {
                    "mode": {"not": {"const": "inherit"}},
                    **{stage: {"enum": ["disable", "require"]} for stage in stages},
                }
            },
            {
                "if": {"properties": {"mode": {"const": "none"}}},
                "then": {
                    "properties": {
                        "selectors": {"maxItems": 0},
                        **{stage: {"const": "disable"} for stage in stages},
                    }
                },
            },
            {
                "if": {"properties": {"mode": {"enum": ["selected", "exhaustive"]}}},
                "then": {"required": ["selectors"], "properties": {"selectors": {"minItems": 1}}},
            },
            {
                "if": {"properties": {"mode": {"const": "exhaustive"}}},
                "then": {
                    "properties": {
                        "selectors": {
                            "items": {
                                "required": ["coverage_profile", "max_items"],
                                "properties": {
                                    "coverage_profile": {"type": "string"},
                                    "max_items": {"type": "integer"},
                                },
                            }
                        }
                    }
                },
            },
            {
                "if": {"anyOf": [{"properties": {stage: {"const": "require"}}} for stage in ("retention", "export")]},
                "then": {"properties": {"collection": {"const": "require"}}},
            },
            {
                "if": {"properties": {"mode": {"const": "operational-only"}}},
                "then": {
                    "properties": {
                        "purpose": {"const": "operational"},
                        "retention": {"const": "disable"},
                        "export": {"const": "disable"},
                    }
                },
            },
        ]
    )
    return schema
