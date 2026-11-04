package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// ControlDeclaration carries compiled v1 authority and ordering coordinates.
type ControlDeclaration struct {
	DeclarationRef           string      `json:"declaration_ref"`
	Kind                     string      `json:"kind"`
	ParticipantAddress       string      `json:"participant_address"`
	EpisodeID                string      `json:"episode_id"`
	ControllerRef            string      `json:"controller_ref"`
	ControllerStateRef       string      `json:"controller_state_ref"`
	AuthorityBasisRefs       []string    `json:"authority_basis_refs"`
	ControlledScopeRefs      []string    `json:"controlled_scope_refs"`
	BehaviorSpecificationRef string      `json:"behavior_specification_ref"`
	MixedControlPolicyRef    string      `json:"mixed_control_policy_ref"`
	PolicyRevision           string      `json:"policy_revision"`
	ExpectedStateRevision    json.Number `json:"expected_state_revision"`
	EffectiveOrder           json.Number `json:"effective_order"`
	ValidFromOrder           json.Number `json:"valid_from_order"`
	ValidUntilOrder          json.Number `json:"valid_until_order"`
}

// ControlTarget fixes a trusted target's exact kind, revision and scope.
type ControlTarget struct {
	Kind               string      `json:"target_kind"`
	Reference          string      `json:"target_ref"`
	Revision           json.Number `json:"target_revision"`
	ParticipantAddress string      `json:"participant_address"`
	EpisodeID          string      `json:"episode_id"`
}

// ControlOccurrenceContext supplies the complete v1 record set and compiled
// coordinates. It does not establish action admission or execution.
type ControlOccurrenceContext interface {
	ControlOccurrences() [][]byte
	ControlDeclarations() []ControlDeclaration
	ControlTargets() []ControlTarget
}

type controlOccurrenceIndex struct {
	declarations, records, proposals, targets map[string]any
	decisions                                 map[string]bool
}

func (e *Validator) controlOccurrenceRules() map[string]definition {
	return map[string]definition{
		"participant-control-occurrence-context-agreement":    {check: e.controlOccurrence, contextual: true, requiresContext: true},
		"participant-control-occurrence-v2-context-agreement": {check: e.controlOccurrence, contextual: true, requiresContext: true},
	}
}

func (e *Validator) controlOccurrenceV1(i validation.Invocation) error {
	context, ok := i.Context.(ControlOccurrenceContext)
	if !ok {
		return contextRequired()
	}
	declarations, targets := context.ControlDeclarations(), context.ControlTargets()
	if len(declarations) > 4096 || len(targets) > 4096 {
		return invalid()
	}
	index := controlOccurrenceIndex{declarations: map[string]any{}, records: map[string]any{}, proposals: map[string]any{}, targets: map[string]any{}, decisions: map[string]bool{}}
	if err := index.authorities(declarations, targets); err != nil {
		return err
	}
	records, err := e.experimentDocuments(termParticipantControlOccurrenceV1, context.ControlOccurrences())
	if err != nil {
		return err
	}
	for _, record := range records {
		v, normalizeErr := e.defaulted(termParticipantControlOccurrenceV1, record)
		if normalizeErr != nil {
			return normalizeErr
		}
		if err = index.register(v); err != nil {
			return err
		}
	}
	candidate, err := e.defaulted(termParticipantControlOccurrenceV1, i.Instance)
	if err != nil {
		return err
	}
	if !equal(index.records[stringAt(candidate, "event_id")], candidate) {
		return invalid()
	}
	for _, record := range index.records {
		if err := index.validate(record); err != nil {
			return err
		}
	}
	return nil
}

func controlCoordinateDocument(v any) (any, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return nil, invalid()
	}
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 32}, ingress.Object)
	if err != nil {
		return nil, invalid()
	}
	return value, nil
}

func (index *controlOccurrenceIndex) authorities(declarations []ControlDeclaration, targets []ControlTarget) error {
	for _, declaration := range declarations {
		v, err := controlCoordinateDocument(declaration)
		if err != nil {
			return err
		}
		if err := controlDeclarationShape(v); err != nil {
			return err
		}
		key := join(stringAt(v, "declaration_ref"), stringAt(v, fieldParticipantAddress), stringAt(v, fieldEpisodeID))
		if prior := index.declarations[key]; prior != nil && !equal(prior, v) {
			return invalid()
		}
		index.declarations[key] = v
	}
	for _, target := range targets {
		v, err := controlCoordinateDocument(target)
		if err != nil {
			return err
		}
		if err := index.target(v); err != nil {
			return err
		}
	}
	return nil
}

func controlDeclarationShape(v any) error {
	for _, field := range []string{"declaration_ref", fieldParticipantAddress, fieldEpisodeID, "controller_ref", "controller_state_ref", "behavior_specification_ref", "mixed_control_policy_ref", "policy_revision"} {
		if stringAt(v, field) == "" {
			return invalid()
		}
	}
	for _, field := range []string{termExpectedStateRevision, "effective_order", termValidFromOrder, termValidUntilOrder} {
		value, ok := number(at(v, field))
		if !ok || !value.IsInt() || value.Sign() < 0 {
			return invalid()
		}
	}
	if !effectiveInterval(v) || !fieldsUnique(v, "authority_basis_refs", "controlled_scope_refs") || len(array(at(v, "authority_basis_refs"))) == 0 || len(array(at(v, "controlled_scope_refs"))) == 0 {
		return invalid()
	}
	return require(controlTransitionKind(stringAt(v, termKind)))
}

func controlTransitionKind(kind string) bool {
	return map[string]bool{termProposal: true, termApproval: true, termDenial: true, termExternalDirection: true, termIntervention: true, termHandoff: true, termOverride: true, termCancellation: true}[kind]
}

func (index *controlOccurrenceIndex) target(v any) error {
	kind := stringAt(v, termTargetKind)
	valid := map[string]bool{termProposal: true, termDecision: true, messageControl: true, "action": true, "admitted-action": true, termAttempt: true}[kind]
	revision, ok := number(at(v, termTargetRevision))
	if !valid || !ok || !revision.IsInt() || revision.Sign() <= 0 || stringAt(v, termTargetRef) == "" || stringAt(v, fieldParticipantAddress) == "" || stringAt(v, fieldEpisodeID) == "" {
		return invalid()
	}
	key := join(kind, stringAt(v, termTargetRef))
	if prior := index.targets[key]; prior != nil && !equal(prior, v) {
		return invalid()
	}
	index.targets[key] = v
	return nil
}

func (index *controlOccurrenceIndex) producedTarget(record any, kind string, reference, revision any) error {
	return index.target(map[string]any{termTargetKind: kind, termTargetRef: reference, termTargetRevision: revision, fieldParticipantAddress: at(record, fieldParticipantAddress), fieldEpisodeID: at(record, fieldEpisodeID)})
}

func (index *controlOccurrenceIndex) register(record any) error {
	id := stringAt(record, "event_id")
	if previous := index.records[id]; previous != nil {
		return require(equal(previous, record))
	}
	index.records[id] = record
	occurrence := at(record, "occurrence")
	if stringAt(occurrence, "disposition") == termRejected {
		return nil
	}
	if err := index.producedTarget(record, messageControl, at(record, "event_id"), at(occurrence, "occurrence_revision")); err != nil {
		return err
	}
	switch stringAt(occurrence, termKind) {
	case termProposal:
		proposal := stringAt(occurrence, "proposal_id")
		if previous := index.proposals[proposal]; previous != nil && !equal(previous, record) {
			return invalid()
		}
		index.proposals[proposal] = record
		return index.producedTarget(record, termProposal, at(occurrence, "proposal_id"), at(occurrence, "proposal_revision"))
	case termApproval, termDenial:
		decision := stringAt(occurrence, termDecisionRef)
		if index.decisions[decision] {
			return invalid()
		}
		index.decisions[decision] = true
		return index.producedTarget(record, termDecision, at(occurrence, termDecisionRef), at(occurrence, "decision_revision"))
	}
	return nil
}
