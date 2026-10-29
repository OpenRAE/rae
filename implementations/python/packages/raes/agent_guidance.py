"""Machine-readable RAES agent guidance profile."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from raes_contracts.errors import OperationalError

_GUIDANCE_RELATIVE_PATH = Path("specs") / "agent-guidance" / "agent-guidance.yaml"
_ALLOWED_AUDIENCES = frozenset({"all", "contributor", "operator"})


def agent_guidance(*, audience: str = "all") -> dict[str, Any]:
    """Return the AUT-811 guidance profile, optionally filtered by audience."""
    audience_key = audience.strip().lower() if audience else "all"
    if audience_key not in _ALLOWED_AUDIENCES:
        return {
            "status": "invalid",
            "stage": "guidance_filter",
            "diagnostics": [
                {
                    "stage": "guidance_filter",
                    "severity": "error",
                    "code": "agent_guidance.audience",
                    "message": "audience must be one of: all, contributor, operator",
                }
            ],
        }

    profile = _load_profile()
    filtered = _filter_profile(profile, audience_key)
    return {"status": "ok", "audience": audience_key, **filtered}


def _load_profile() -> dict[str, Any]:
    path = _find_repo_root(Path(__file__).resolve().parent) / _GUIDANCE_RELATIVE_PATH
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a YAML mapping")
    return data


def _filter_profile(profile: dict[str, Any], audience: str) -> dict[str, Any]:
    data = deepcopy(profile)
    if audience == "all":
        return data

    guidance = data.get("guidance")
    if not isinstance(guidance, dict):
        return data
    for category, entries in guidance.items():
        if not isinstance(entries, list):
            continue
        guidance[category] = [
            entry
            for entry in entries
            if isinstance(entry, dict) and audience in {str(item) for item in entry.get("audience", [])}
        ]
    return data


def _find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".ground-control.yaml").exists() or (candidate / ".git").exists():
            return candidate
    # An installed distribution has no repository checkout, so the guidance resource is unavailable.
    raise OperationalError(f"could not locate RAES repo root from {start}")
