package admission

import (
	"math/big"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func paired(v any, ref, revision string) bool { return (at(v, ref) == nil) == (at(v, revision) == nil) }

func behavioralProfile(i validation.Invocation) error {
	v := i.Instance
	if !sortedUnique(rowIDs(at(v, "source_refs"), "source_ref")) {
		return invalid()
	}
	parameters := at(v, "parameters")
	switch stringAt(parameters, termKind) {
	case crossingKind, crossingMultiKind:
		return crossingProfile(v, parameters)
	case "participant-predicate-opacity/v1":
		if stringAt(v, fieldRelationID) != "participant-predicate-opacity" || !equal(at(v, fieldObservationProjectionRef), at(parameters, termObservation, "projection_ref")) || !equal(at(v, fieldObservationProjectionRevision), at(parameters, termObservation, "projection_revision")) {
			return invalid()
		}
		finite := stringAt(parameters, "carrier", termKind) == "finite-possible-points"
		if finite != (stringAt(v, "finite_analysis_scope") == "declared-complete-finite-carrier") {
			return invalid()
		}
		return opacityParameters(parameters)
	default:
		return invalid()
	}
}
func crossingProfile(profile, parameters any) error {
	multi := stringAt(parameters, termKind) == crossingMultiKind
	id, revision, projection := "participant-crossing-dpbb-finite-v1", "rev2", "participant-crossing-projection"
	if multi {
		id, revision, projection = "participant-crossing-multi-operation-dpbb-finite-v1", termRev1, "participant-crossing-multi-operation-projection"
	}
	for field, expected := range map[string]string{termProfileID: id, "profile_revision": revision, fieldTaxonomyRevision: "rev8", fieldRelationID: "divergence-preserving-branching-bisimulation", fieldLeftCarrierRef: stringAt(parameters, "left", "model_id"), fieldObservationProjectionRef: projection, fieldObservationProjectionRevision: termRev1, "finite_analysis_scope": "declared-complete-finite-carrier"} {
		if stringAt(profile, field) != expected {
			return invalid()
		}
	}
	return require(!equal(at(parameters, "left", "source_digest"), at(parameters, "right", "source_digest")))
}
func opacityParameters(v any) error {
	for _, path := range [][]string{{"scheduler_refs"}, {"environment_refs"}, {termObservation, "observable_channels"}, {termOrder, "order_refs"}, {"strategy", "strategy_refs"}, {"observer", "member_refs"}} {
		if !sortedUnique(stringsOf(at(v, path...))) {
			return invalid()
		}
	}
	if !paired(at(v, "memory"), "reset_rule_ref", "reset_rule_revision") || !paired(at(v, "time"), "opportunity_basis_ref", "opportunity_basis_revision") {
		return invalid()
	}
	if boolean(at(v, "time", "absence_observable")) != (at(v, "time", "opportunity_basis_ref") != nil) {
		return invalid()
	}
	if (stringAt(v, "horizon", "scope") == "historical-k") != (at(v, "horizon", "steps") != nil) {
		return invalid()
	}
	finite := stringAt(v, "carrier", termKind) == "finite-possible-points"
	if finite != (at(v, "bounds") != nil) {
		return invalid()
	}
	if !finite {
		return nil
	}
	strategies := 1
	if stringAt(v, "strategy", termKind) == termActive {
		strategies = len(array(at(v, "strategy", "strategy_refs")))
	}
	for field, count := range map[string]int{"max_strategies": strategies, "max_order_variants": len(array(at(v, termOrder, "order_refs"))), "max_scheduler_environment_pairs": len(array(at(v, "scheduler_refs"))) * len(array(at(v, "environment_refs")))} {
		bound, ok := number(at(v, "bounds", field))
		if !ok || bound.Cmp(big.NewRat(int64(count), 1)) < 0 {
			return invalid()
		}
	}
	return nil
}
func claimStrength(v any) error {
	if !paired(v, fieldObservationProjectionRef, fieldObservationProjectionRevision) || !paired(v, "relation_parameter_profile_ref", "relation_parameter_profile_revision") {
		return invalid()
	}
	evidence, status, axis := stringAt(v, "evidence_scope"), stringAt(v, "assurance_status"), stringAt(v, "assurance_axis")
	switch stringAt(v, "quantifier_scope") {
	case "all-admitted-inputs", "all-traces", "all-strategies":
		if evidence != evidenceModelCheck && evidence != evidenceProof {
			return invalid()
		}
	}
	if axis != "" {
		return claimAssurance(axis, status, evidence)
	}
	if status == assuranceEnforced || status == assuranceDeclared || status == assuranceRealized || status == assuranceConformant {
		return invalid()
	}
	return require((status != assuranceProved || evidence == evidenceProof) && (status != assuranceModelChecked || evidence == evidenceModelCheck))
}
func claimAssurance(axis, status, evidence string) error {
	if status == statusFuture || axis == evidenceProof && status == "deliberately-unproved" {
		return require(evidence == strengthStructural)
	}
	rules := map[string][]string{
		"definition": {"defined", strengthStructural}, "checker": {statusImplemented, strengthStructural, evidenceFinite}, "bounded-test": {statusTested, evidenceFinite}, evidenceModelCheck: {assuranceModelChecked, evidenceModelCheck}, evidenceProof: {assuranceProved, evidenceProof}, "runtime-enforcement": {assuranceEnforced, strengthStructural, evidenceFinite}, "backend-declaration": {assuranceDeclared, strengthStructural}, "backend-realization": {assuranceRealized, strengthStructural, evidenceFinite}, "backend-conformance": {assuranceConformant, evidenceFinite, "statistical"},
	}
	rule := rules[axis]
	if len(rule) == 0 || status != rule[0] {
		return invalid()
	}
	return require(slices.Contains(rule[1:], evidence))
}
