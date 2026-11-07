package admission

import (
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

// CrossingContext supplies the exact stage records, typed references and
// independently known evidence and authority sets for one crossing history.
type CrossingContext interface {
	CrossingOccurrences() [][]byte
	CrossingSubjects() [][]byte
	CrossingPolicies() [][]byte
	CrossingEvidenceRefs() []string
	CrossingAuthorityRefs() []string
}

type crossingIndex struct {
	records, stages, subjects, policies map[string]any
	evidence, authority                 map[string]bool
}

func (e *Validator) crossingRules() map[string]definition {
	return map[string]definition{"participant-crossing-context-agreement": {check: e.crossingContext, contextual: true, requiresContext: true}}
}

func (e *Validator) crossingContext(i validation.Invocation) error {
	context, ok := i.Context.(CrossingContext)
	if !ok {
		return contextRequired()
	}
	index, err := e.crossingContextIndex(context)
	if err != nil {
		return err
	}
	v, err := e.defaulted(termParticipantCrossingOccurrenceV1, i.Instance)
	if err != nil {
		return err
	}
	if !equal(index.records[stringAt(v, "event_id")], v) {
		return invalid()
	}
	for _, record := range index.records {
		if err := index.common(record); err != nil {
			return err
		}
		if err := index.stage(record); err != nil {
			return err
		}
	}
	return index.transformations()
}

func (e *Validator) crossingContextIndex(context CrossingContext) (*crossingIndex, error) {
	evidence, authority := context.CrossingEvidenceRefs(), context.CrossingAuthorityRefs()
	if len(evidence) > 100000 || len(authority) > 100000 {
		return nil, invalid()
	}
	index := &crossingIndex{records: map[string]any{}, stages: map[string]any{}, subjects: map[string]any{}, policies: map[string]any{}, evidence: set(jsonStrings(evidence)), authority: set(jsonStrings(authority))}
	subjects, err := e.crossingFragments("ParticipantCrossingSubjectReferenceModel", context.CrossingSubjects())
	if err != nil {
		return nil, err
	}
	for _, subject := range subjects {
		if err = index.subject(subject); err != nil {
			return nil, err
		}
	}
	policies, err := e.crossingFragments("ParticipantCrossingPolicyReferenceModel", context.CrossingPolicies())
	if err != nil {
		return nil, err
	}
	for _, policy := range policies {
		if err = index.policy(policy); err != nil {
			return nil, err
		}
	}
	if err = e.crossingRecords(index, context.CrossingOccurrences()); err != nil {
		return nil, err
	}
	return index, nil
}

func (e *Validator) crossingFragments(name string, raw [][]byte) ([]any, error) {
	if len(raw) > 4096 {
		return nil, invalid()
	}
	remaining := 64 * 1048576
	result := make([]any, 0, len(raw))
	for _, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := e.low.DecodeObjectFragment(termParticipantCrossingOccurrenceV1, schemaDefinitionsPrefix+name, data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
		if err != nil {
			return nil, err
		}
		result = append(result, v)
	}
	return result, nil
}

func crossingSubjectKey(v any) string {
	return join(stringAt(v, "subject_kind"), stringAt(v, "subject_ref"))
}

func (index *crossingIndex) register(record any) error {
	event := stringAt(record, "event_id")
	if previous := index.records[event]; previous != nil {
		return require(equal(previous, record))
	}
	index.records[event] = record
	stage := stringAt(record, "occurrence", "stage")
	field := map[string]string{termRequested: "request_id", termDecided: termDecisionID, termTransformed: "transformation_id", termDisclosed: "disclosure_id", termDeliveryAttempted: termAttemptID, termDelivered: "delivery_id", basisObserved: termObservationID}[stage]
	if field == "" {
		return nil
	}
	key := join(stage, stringAt(record, "occurrence", field))
	if previous := index.stages[key]; previous != nil && !equal(previous, record) {
		return invalid()
	}
	index.stages[key] = record
	return nil
}

func (index *crossingIndex) common(record any) error {
	v := at(record, "occurrence")
	subjects := []any{at(v, "subject")}
	if stringAt(v, "stage") == termTransformed {
		subjects = append(subjects, at(v, "source_subject"), at(v, "result_subject"))
	}
	for _, subject := range subjects {
		if !equal(index.subjects[crossingSubjectKey(subject)], subject) {
			return invalid()
		}
	}
	policy := at(v, termPolicy)
	if !equal(index.policies[join(stringAt(policy, "policy_id"), stringAt(policy, "policy_revision"))], policy) || !subset(stringsOf(at(record, "evidence_refs")), index.evidence) || !subset(stringsOf(at(v, termAuthorityBasisRefs)), index.authority) {
		return invalid()
	}
	if stringAt(v, "stage") == termRequested || stringAt(v, "stage") == termDecided {
		if !subset(stringsOf(at(v, "required_evidence_refs")), index.evidence) {
			return invalid()
		}
	}
	if stringAt(v, "stage") == termAudited && !subset(stringsOf(at(v, "retained_evidence_refs")), index.evidence) {
		return invalid()
	}
	return index.declassificationAuthority(v)
}

func (index *crossingIndex) transformations() error {
	edges := map[string][]string{}
	for _, record := range index.records {
		v := at(record, "occurrence")
		if stringAt(v, "stage") != termTransformed {
			continue
		}
		source, result := crossingSubjectKey(at(v, "source_subject")), crossingSubjectKey(at(v, "result_subject"))
		if previous := edges[source]; len(previous) > 0 && previous[0] != result {
			return invalid()
		}
		edges[source] = []string{result}
	}
	return require(!graph.HasCycle(edges))
}

func (index *crossingIndex) subject(subject any) error {
	for _, field := range []string{"subject_revision", "subject_digest"} {
		if _, present := object(subject)[field]; !present {
			object(subject)[field] = nil
		}
	}
	key := crossingSubjectKey(subject)
	if previous := index.subjects[key]; previous != nil && !equal(previous, subject) {
		return invalid()
	}
	index.subjects[key] = subject

	return nil
}

func (index *crossingIndex) policy(policy any) error {
	if !effectiveInterval(policy) {
		return invalid()
	}
	key := join(stringAt(policy, "policy_id"), stringAt(policy, "policy_revision"))
	if previous := index.policies[key]; previous != nil && !equal(previous, policy) {
		return invalid()
	}
	index.policies[key] = policy

	return nil
}

func (index *crossingIndex) declassificationAuthority(v any) error {
	if basis := at(v, "declassification_basis_ref"); basis != nil {
		if !index.authority[text(basis)] || !set(at(v, termAuthorityBasisRefs))[text(basis)] {
			return invalid()
		}
	}
	return nil
}

func (e *Validator) crossingRecords(index *crossingIndex, raw [][]byte) error {
	records, err := e.experimentDocuments(termParticipantCrossingOccurrenceV1, raw)
	if err != nil {
		return err
	}
	for _, record := range records {
		normal, err := e.defaulted(termParticipantCrossingOccurrenceV1, record)
		if err != nil {
			return err
		}
		if err := index.register(normal); err != nil {
			return err
		}
	}

	return nil
}
