"""Select exactly the records that can participate in temporal validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from rpds import HashTrieMap, HashTrieSet

from .canonical import JsonValue


def explicit_temporal_record(record: Mapping[str, object]) -> bool:
    contexts = record.get("temporal_contexts", ())
    # Stored history is input to its validator, so a malformed context list is a refusal (ADR-116 rule E3).
    if not isinstance(contexts, list | tuple) or not all(isinstance(item, Mapping) for item in contexts):
        raise ValueError("temporal contexts must be a list of objects")
    return bool(record.get("temporal_assessments") or any(item.get("shared_time") for item in contexts))


@dataclass(frozen=True)
class TemporalRecordIndex:
    by_action: HashTrieMap = HashTrieMap()
    explicit_actions: HashTrieSet = HashTrieSet()
    valid: bool = True

    def append(self, position: int, record: Mapping[str, object]) -> TemporalRecordIndex:
        key = (record.get("episode_id"), record.get("action_instance_id"))
        try:
            explicit = explicit_temporal_record(record)
            records = self.by_action.get(key, HashTrieMap()).insert(position, record)
        # An unhashable identity or a malformed context list is malformed public input,
        # which must still meet the exhaustive validator.
        except TypeError, ValueError:
            return TemporalRecordIndex(self.by_action, self.explicit_actions, False)
        return TemporalRecordIndex(
            self.by_action.insert(key, records),
            self.explicit_actions.insert(key) if explicit else self.explicit_actions,
            self.valid,
        )

    def records(self) -> tuple[JsonValue, ...] | None:
        if not self.valid:
            return None
        selected = {}
        for key in self.explicit_actions:
            selected.update(self.by_action[key])
        from .immutable_history import mutable_history_value

        return tuple(mutable_history_value(record) for _, record in sorted(selected.items()))
