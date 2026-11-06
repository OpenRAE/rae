package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// ControlCommittedIntent binds a prior committed evaluation to its owner outcome.
type ControlCommittedIntent struct {
	Evaluation, Outcome []byte
}

// ControlInjectOwner is the compiled SDL owner's delivery projection. Digest
// identifies the full original delivery, including fields outside this projection.
type ControlInjectOwner struct {
	Digest, ParticipantAddress, InjectRef, EventRef, ScriptRef, StoryRef string
	SourceItemRef, ResultItemRef, DisclosureRef, AudienceScopeRef        string
	Controlled                                                           bool
	Coordinates                                                          []byte
	Application                                                          validation.Value
}

// ControlResolutionSnapshot holds independent owner resolutions. Raw fragments
// use the published control models. Support keys are obligation and instance IDs.
type ControlResolutionSnapshot struct {
	AdmittedRequest, AdmittedCrossing, IncumbentGateEvidence []byte
	IncumbentGateDisposition                                 string
	SafeReferences                                           [][]byte
	InstalledBindings, EffectiveSupport, ResolvedResults     map[string][]byte
	ResolvedCoverage, AuthorizedEffects, RealizationReceipts map[string][]byte
	ResolvedSupport                                          map[[2]string][]byte
	AuthorizedStateProposals                                 map[string][]byte
	ParentAdmissionReceipt, ParentApplicationReceipt         []byte
	CommitReceipt                                            []byte
	CommittedIntents                                         map[string]ControlCommittedIntent
	FlowRelations                                            map[string]validation.Value
	InjectOwners                                             map[string]ControlInjectOwner
}

// ControlResolutionContext supplies admitted owner records and narrow support
// decisions. Payload claims cannot construct this authority. Methods perform no
// lookup on behalf of admission and must be safe for the caller's concurrency.
type ControlResolutionContext interface {
	CrossingContext
	ControlOccurrenceContext
	ControlResolutionSnapshot() ControlResolutionSnapshot
	ControlDeclaredSupport(binding, support json.RawMessage) (string, error)
	ControlSatisfiedSupport(support json.RawMessage) (bool, error)
}

type controlResolution struct {
	owner    *Validator
	id       string
	v2       bool
	context  ControlResolutionContext
	snapshot ControlResolutionSnapshot
	request  any
	indexes  map[string]map[string]any
	safe     map[string]bool
}

func (e *Validator) controlResolutionRules() map[string]definition {
	return map[string]definition{"participant-control-resolved-context": {check: e.controlResolvedContext, contextual: true, requiresContext: true}}
}

func (e *Validator) controlResolvedContext(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(ControlResolutionContext)
	if !ok {
		return contextRequired()
	}
	v, err := e.defaulted(i.Key.ContractID, i.Instance)
	if err != nil {
		return err
	}
	r := controlResolution{owner: e, id: i.Key.ContractID, v2: i.Key.ContractID == termParticipantControlEvaluationV2, context: context, snapshot: context.ControlResolutionSnapshot(), indexes: map[string]map[string]any{}}
	if err = r.load(); err != nil {
		return err
	}
	if !equal(at(v, "request"), r.request) {
		return invalid()
	}
	if err = r.references(v); err != nil {
		return err
	}
	if err = r.incumbents(at(v, "request", "context")); err != nil {
		return err
	}
	if r.v2 {
		return r.validateV2(v)
	}
	return r.validateV1(v)
}
