package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func (e *Validator) snapshotLocalModels(v any) error {
	if !materializationRecordsUnique(at(v, "materialization_attestations")) {
		return invalid()
	}
	for key, entry := range object(at(v, "entries")) {
		if key != stringAt(entry, "address") {
			return invalid()
		}
	}
	for _, state := range object(at(v, "participant_execution_services")) {
		data, err := json.Marshal(state)
		if err != nil {
			return err
		}
		view, err := e.low.DefaultedObjectFragment(termRuntimeSnapshotV1, "#/$defs/ParticipantExecutionServiceStateModel", data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
		if err != nil {
			return err
		}
		if err := executionState(view); err != nil {
			return err
		}
	}
	return nil
}
