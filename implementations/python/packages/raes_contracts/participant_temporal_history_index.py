"""Select exactly the records that can participate in temporal validation."""

from __future__ import annotations

from dataclasses import dataclass

from rpds import HashTrieMap, HashTrieSet


def explicit_temporal_record(record) -> bool:
    return bool(
        record.get("temporal_assessments")
        or any(item.get("shared_time") for item in record.get("temporal_contexts", ()))
    )


@dataclass(frozen=True)
class TemporalRecordIndex:
    by_action: HashTrieMap = HashTrieMap()
    explicit_actions: HashTrieSet = HashTrieSet()
    valid: bool = True

    def append(self, position: int, record):
        key = (record.get("episode_id"), record.get("action_instance_id"))
        try:
            explicit = explicit_temporal_record(record)
            records = self.by_action.get(key, HashTrieMap()).insert(position, record)
        except (TypeError, AttributeError):
            # Malformed public input must still meet the exhaustive validator.
            return TemporalRecordIndex(self.by_action, self.explicit_actions, False)
        return TemporalRecordIndex(
            self.by_action.insert(key, records),
            self.explicit_actions.insert(key) if explicit else self.explicit_actions,
            self.valid,
        )

    def records(self):
        if not self.valid:
            return None
        selected = {}
        for key in self.explicit_actions:
            selected.update(self.by_action[key])
        from .immutable_history import mutable_history_value

        return tuple(mutable_history_value(record) for _, record in sorted(selected.items()))
