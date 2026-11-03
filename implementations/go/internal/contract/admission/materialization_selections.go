package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func materializationProvenanceKey(row any) string {
	return join(stringAt(row, "address"), stringAt(row, "field_path"), stringAt(row, "domain"), stringAt(row, "requirement_kind"))
}
func materializationSelectionKey(row any) string {
	return join(stringAt(row, "address"), stringAt(row, "field_path"), stringAt(row, "requirement_kind"))
}
func (r *materializationInventory) selections() error {
	current := rowSet(at(r.report, "descendants"), "address")
	affected, unchanged := map[string]bool{}, map[string]bool{}
	for _, operation := range array(at(r.execution.plan, "operations")) {
		key := stringAt(operation, "address")
		if stringAt(operation, "action") == termUnchanged {
			unchanged[key] = true
		} else {
			affected[key] = true
		}
	}
	ledger := r.baseProvenance(current, affected)
	if err := r.descendantProvenance(ledger); err != nil {
		return err
	}
	for _, row := range array(at(r.execution.previous, "realization_provenance")) {
		if key := stringAt(row, "address"); unchanged[key] && r.entries[key] != nil {
			ledger[materializationProvenanceKey(row)] = row
		}
	}
	choices := materializationAdmittedChoices(r.execution.plan)
	identities := map[string]any{}
	for _, row := range ledger {
		identities[materializationSelectionKey(row)] = row
	}
	for _, selection := range array(at(r.report, "backend_selections")) {
		key := materializationSelectionKey(selection)
		row := identities[key]
		if row == nil || stringAt(row, "explicitness") == postureExact || !choices[key] && !current[stringAt(selection, "address")] {
			return invalid()
		}
	}
	return nil
}
func (r *materializationInventory) descendantProvenance(ledger map[string]any) error {
	for _, record := range array(at(r.report, "descendants")) {
		if stringAt(record, "state") == termAutoremoved {
			continue
		}
		address := stringAt(record, "address")
		for _, raw := range r.execution.current.concerns[address] {
			row, err := r.execution.owner.low.DefaultedObjectFragment(termRuntimeSnapshotV1, "#/$defs/RealizationProvenanceEntryModel", raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
			if err != nil {
				return err
			}
			if stringAt(row, "address") != address || stringAt(row, "explicitness") != termOpen || stringAt(row, "provenance") != "backend-realized" {
				return invalid()
			}
			ledger[materializationProvenanceKey(row)] = row
		}
	}
	return nil
}

func materializationJSON(raw json.RawMessage) (any, error) {
	return ingress.Parse(raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
}

func materializationAdmittedChoices(plan any) map[string]bool {
	choices := map[string]bool{}
	for _, row := range array(at(plan, "realization_authority")) {
		if mode := stringAt(row, "mode"); mode == termOpen || mode == termConstrained {
			choices[materializationSelectionKey(row)] = true
		}
	}
	for _, row := range array(at(plan, "realization_constraints")) {
		if posture := stringAt(row, "posture"); posture == termOpen || posture == termConstrained {
			choices[join(stringAt(row, "address"), stringAt(row, "field_path"), stringAt(row, "concern"))] = true
		}
	}
	return choices
}

func (r *materializationInventory) baseProvenance(current, affected map[string]bool) map[string]any {
	ledger := map[string]any{}
	for _, row := range array(at(r.execution.previous, "realization_provenance")) {
		key := stringAt(row, "address")
		if !current[key] && !affected[key] && r.entries[key] != nil {
			ledger[materializationProvenanceKey(row)] = row
		}
	}
	for _, row := range array(at(r.execution.actual, "realization_provenance")) {
		key := stringAt(row, "address")
		if !current[key] && r.entries[key] != nil {
			ledger[materializationProvenanceKey(row)] = row
		}
	}
	return ledger
}
