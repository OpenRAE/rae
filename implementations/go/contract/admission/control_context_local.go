package admission

import "github.com/OpenRAE/rae/implementations/go/internal/base/urisafety"

func controlContextLocal(id string, v any) error {
	if !fieldsUnique(v, "evidence_refs", "provenance_refs") {
		return invalid()
	}
	switch id {
	case termParticipantControlContextAssetV1:
		if !fieldsUnique(v, "participant_addresses", "role_refs") || len(array(at(v, "participant_addresses")))+len(array(at(v, "role_refs"))) == 0 {
			return invalid()
		}
		return require(urisafety.Check(stringAt(v, "content", "uri"), urisafety.Options{}) == nil)
	case termParticipantControlContextChangeV1:
		successor := at(v, "successor_ref")
		if (successor != nil) != (stringAt(v, "operation") == "replace") {
			return invalid()
		}
		return require(successor == nil || equal(at(successor, "asset_id"), at(v, "asset_ref", "asset_id")) && !equal(at(successor, "asset_version"), at(v, "asset_ref", "asset_version")))
	case termParticipantControlContextRecordV1:
		return controlContextRecordShape(v)
	}
	return nil
}

func controlContextDefaults(v any) {
	if stringAt(v, termSchemaVersion) == "participant-control-context-asset/v1" {
		for _, field := range []string{"participant_addresses", "role_refs"} {
			if at(v, field) == nil {
				object(v)[field] = []any{}
			}
		}
		if at(v, "content", "satisfies_refs") == nil {
			object(at(v, "content"))["satisfies_refs"] = []any{}
		}
	}
	for _, field := range []string{"record_cut", "selection_cut", "effective_cut"} {
		cut := at(v, field)
		if stringAt(cut, "cut_kind") == termSequencePrefix && at(cut, "predecessor_event_refs") == nil {
			object(cut)["predecessor_event_refs"] = []any{}
		}
	}
}

func controlContextRecordShape(v any) error {
	required := map[string]map[string]bool{termSelected: {}, termWithheld: {"withholding_authority_ref": true}, termDisclosed: {termSurfaceID: true, termItemRef: true}, termDelivered: {termSurfaceID: true, termItemRef: true, termDeliveryRef: true}}[stringAt(v, "disposition")]
	if required == nil {
		return invalid()
	}
	for _, field := range []string{"withholding_authority_ref", termSurfaceID, termItemRef, termDeliveryRef} {
		if (at(v, field) != nil) != required[field] {
			return invalid()
		}
	}
	return nil
}
