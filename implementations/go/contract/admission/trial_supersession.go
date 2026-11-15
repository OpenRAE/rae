package admission

import (
	"encoding/json"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// SupersedeTrialRunJSON constructs the immutable status-only archival successor.
// Original outcomes and evidence remain attached to their original version.
func SupersedeTrialRunJSON(v *Validator, run []byte, child validation.Value) ([]byte, error) {
	plan, err := v.experimentValue(child, trialPlanContract)
	if err != nil {
		return nil, err
	}
	return v.supersededRunProjection(run, plan)
}
func (e *Validator) supersededRunProjection(raw []byte, child any) ([]byte, error) {
	origin := at(child, "replacement_origin")
	entries := object(at(child, "entries"))
	if origin == nil || len(entries) != 1 {
		return nil, invalid()
	}
	raw, err := e.experimentProjection(termExperimentRunV1, raw)
	if err != nil {
		return nil, err
	}
	var payload map[string]any
	if decodeExact(raw, &payload) != nil {
		return nil, invalid()
	}
	version, id := stringAt(payload, "run_version"), stringAt(payload, termRunID)
	payload["run_version"] = version + ".superseded-" + strconv.Itoa(countAt(origin, "ordinal"))
	payload["run_status"] = statusSuperseded
	payload["validation_basis_disclosures"], payload["evidence_requirement_relations"] = []any{}, []any{}
	invalidation := object(payload["invalidation"])
	if invalidation == nil {
		invalidation = map[string]any{"invalidated_at": payload["ended_at"], "reason": "failed trial replaced under the admitted experiment policy"}
	}
	var entry any
	for _, value := range entries {
		entry = value
	}
	invalidation["superseded_by"] = map[string]any{fieldRefKind: kindRun, fieldRefID: at(entry, termRunID), fieldRefVersion: "1"}
	payload["invalidation"] = invalidation
	reference := map[string]any{fieldRefKind: kindRun, fieldRefID: id, fieldRefVersion: version}
	derived := array(payload["derived_from_refs"])
	present := false
	for _, ref := range derived {
		present = present || equal(ref, reference)
	}
	if !present {
		derived = append(derived, reference)
	}
	payload["derived_from_refs"] = derived
	raw, err = json.Marshal(payload)
	if err != nil {
		return nil, invalid()
	}
	return e.experimentProjection(termExperimentRunV1, raw)
}
