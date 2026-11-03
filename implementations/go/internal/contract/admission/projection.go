package admission

import (
	"encoding/json"
	"maps"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) projectionPartition(i validation.Invocation) error {
	v, err := e.defaulted("semantic-projection-report-v1", i.Instance)
	if err != nil {
		return err
	}
	frame, summary := at(v, "frame"), at(v, "summary")
	if checkErr := projectionFrame(frame); checkErr != nil {
		return checkErr
	}
	digest, err := jsonDigest(frame)
	if err != nil {
		return err
	}
	if digest != stringAt(v, "frame_digest") || digest != stringAt(summary, "frame_digest") || !equal(at(summary, "predicate_id"), at(frame, "predicate_profile", "predicate_id")) || !equal(at(summary, "predicate_profile_digest"), at(frame, "predicate_profile", "profile_digest")) {
		return invalid()
	}
	if !orderedRows(at(v, "rows"), "concept_id") {
		return invalid()
	}
	return projectionCounts(v, frame, summary, digest)
}

func projectionFrame(v any) error {
	if !sortedUnique(stringsOf(at(v, "scheme", "included_concept_ids"))) || !sortedUnique(stringsOf(at(v, "subject_scope", "artifact_digests"))) || !orderedRows(at(v, "transformations"), "transformation_id", "transformation_version", "transformation_digest") {
		return invalid()
	}
	profile := at(v, "predicate_profile")
	if err := projectionProfile(profile); err != nil {
		return err
	}
	predicate := stringAt(profile, "predicate_id")
	for _, axis := range []string{termConfiguration, termState} {
		coordinate := at(v, axis)
		if !equal(at(coordinate, "posture"), at(profile, axis+"_axis")) {
			return invalid()
		}
		if stringAt(coordinate, "posture") == notApplicable && stringAt(coordinate, "basis_ref") != predicate+"-"+axis+"-not-applicable" {
			return invalid()
		}
	}
	if stringAt(profile, "transformations_axis") == termForbidden && len(array(at(v, "transformations"))) > 0 {
		return invalid()
	}
	perspective := at(v, "perspective")
	for _, field := range []string{fieldParticipantAddress, fieldEpisodeID, "audience_ref", "projection_policy_id", "projection_policy_revision", "projection_policy_digest", "applicable_cut_ref"} {
		if (stringAt(perspective, "perspective_kind") == termParticipant) != (at(perspective, field) != nil) {
			return invalid()
		}
	}
	return require((stringAt(v, "quantifier", termKind) == "threshold") == (at(v, "quantifier", "threshold") != nil))
}

func projectionProfile(v any) error {
	predicate := stringAt(v, "predicate_id")
	posture := "strict"
	approximate, lossy := boolean(at(v, "allow_approximate_bindings")), boolean(at(v, "allow_lossy_bindings"))
	switch {
	case approximate && lossy:
		posture = "approximate-lossy"
	case approximate:
		posture = "approximate"
	case lossy:
		posture = "lossy"
	}
	producer := map[string]string{"declared": termSdlAuthoringInputV1, "admitted": "validation-basis-disclosure-v1", basisObserved: termPropositionTruthResultV1, statusVerified: "artifact-transformation-report-v1"}[predicate]
	if stringAt(v, termProfileID) != "semantic-projection-"+predicate+"-"+posture+"/v1" || stringAt(v, "profile_version") != "1" || stringAt(v, "adapter_id") != predicate+"-owner-adapter" || stringAt(v, "adapter_version") != "1" || stringAt(v, "producer_contract_id") != producer {
		return invalid()
	}
	adapter, err := jsonDigest(map[string]any{"adapter_id": at(v, "adapter_id"), "adapter_version": at(v, "adapter_version")})
	if err != nil {
		return err
	}
	if adapter != stringAt(v, "adapter_digest") {
		return invalid()
	}
	for axis, applicable := range map[string]bool{termConfiguration: predicate == "declared", termState: predicate == basisObserved, "transformations": predicate == statusVerified} {
		expected := notApplicable
		if axis == "transformations" {
			expected = termForbidden
		}
		if applicable {
			expected = "applicable"
		}
		if stringAt(v, axis+"_axis") != expected {
			return invalid()
		}
	}
	payload := maps.Clone(object(v))
	delete(payload, "profile_digest")
	digest, err := jsonDigest(payload)
	if err != nil {
		return err
	}
	return require(digest == stringAt(v, "profile_digest"))
}

func (e *Validator) projectionWitnesses(i validation.Invocation) error {
	v, err := e.defaulted("semantic-projection-report-v1", i.Instance)
	if err != nil {
		return err
	}
	frame := at(v, "frame")
	for _, row := range array(at(v, "rows")) {
		if !orderedRows(at(row, termBindings), "binding_id") || !sortedUnique(stringsOf(at(row, "reason_codes"))) {
			return invalid()
		}
		if (stringAt(row, "classification") == classificationWitness) != (len(array(at(row, "witnesses"))) > 0) {
			return invalid()
		}
		for _, binding := range array(at(row, termBindings)) {
			if !sortedUnique(stringsOf(at(binding, "loss_details"))) || !sortedUnique(stringsOf(at(binding, "limitations"))) {
				return invalid()
			}
		}
		if err := projectionRowWitnesses(frame, at(row, "witnesses")); err != nil {
			return err
		}
	}

	return nil
}
func projectionRowWitnesses(frame, rows any) error {
	var previous []string
	for _, witness := range array(rows) {
		subject := at(witness, "subject")
		key := []string{stringAt(subject, "canonical_ref"), stringAt(subject, "artifact_digest"), stringAt(witness, "native_result_id"), stringAt(witness, "native_result_digest")}
		if previous != nil && compareTuple(previous, key) >= 0 {
			return invalid()
		}
		previous = key
		for _, field := range []string{"subject_kind", "owning_contract_id", "lifecycle_phase"} {
			if !equal(at(subject, field), at(frame, "subject_scope", field)) {
				return invalid()
			}
		}
		if !set(at(frame, "subject_scope", "artifact_digests"))[stringAt(subject, "artifact_digest")] || !equal(at(witness, "producer_contract_id"), at(frame, "predicate_profile", "producer_contract_id")) || !equal(at(witness, "predicate_profile_digest"), at(frame, "predicate_profile", "profile_digest")) || !sortedUnique(stringsOf(at(witness, "evidence_digests"))) {
			return invalid()
		}
	}

	return nil
}
func projectionCounts(v, frame, summary any, digest string) error {
	included := set(at(frame, "scheme", "included_concept_ids"))
	counts := map[string]int{}
	for _, row := range array(at(v, "rows")) {
		classification := stringAt(row, "classification")
		if included[stringAt(row, "concept_id")] == (classification == classificationExcluded) {
			return invalid()
		}
		counts[classification]++
	}
	total := 0
	for _, class := range []string{classificationWitness, "gap", statusUnknown, "ambiguous", classificationExcluded} {
		if !numericEqual(at(summary, class+"_count"), json.Number(strconv.Itoa(counts[class]))) {
			return invalid()
		}
		if class != classificationExcluded {
			total += counts[class]
		}
	}
	if total != len(included) || !numericEqual(at(summary, "included_denominator"), json.Number(strconv.Itoa(total))) {
		return invalid()
	}
	return require(stringAt(summary, "qualified_fraction") == stringAt(summary, "predicate_id")+":"+strconv.Itoa(counts[classificationWitness])+"/"+strconv.Itoa(total)+"@"+digest)
}
