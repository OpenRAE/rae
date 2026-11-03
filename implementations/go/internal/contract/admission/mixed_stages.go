package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/validation"

// MixedBackendStageSnapshot contains caller-resolved time and composition state.
// PostTimeState's zero value means the owner took no post-invocation readback.
type MixedBackendStageSnapshot struct {
	TimeModelRef, TimeModelDigest       string
	TimeModel, TimeState, PostTimeState validation.Value
	CompositionState                    []byte
}

// MixedBackendStagesContext supplies an invocation's actual immutable transcript.
// Its methods neither dispatch an operation nor grant publication authority.
type MixedBackendStagesContext interface {
	OperationRequest() []byte
	OperationResponses() [][]byte
	OperationControls() [][]byte
	MixedStageBinding() []byte
	MixedStageReports() [][]byte
	MixedStageSnapshot() MixedBackendStageSnapshot
}

type mixedStages struct {
	subject, request, model any
	before                  []any
	confirmed               bool
	fence                   any
	history                 *backendHistory
	reports, responses      []any
	seen                    map[string]any
}

func (e *Validator) mixedStageRules() map[string]definition {
	return map[string]definition{"mixed-backend-stage-transcript": {check: e.mixedStageTranscript, contextual: true, requiresContext: true}}
}

func (e *Validator) mixedStageTranscript(i validation.Invocation) (err error) {
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	context, ok := i.Context.(MixedBackendStagesContext)
	if !ok {
		return contextRequired()
	}
	state, err := e.mixedStageInputs(context)
	if err != nil {
		return err
	}
	candidate, err := e.backendNormalized(termMixedBackendStageReportV1, i.Instance)
	if err != nil {
		return err
	}
	found := false
	for _, report := range state.reports {
		found = found || equal(report, candidate)
	}
	if !found {
		return invalid()
	}
	return state.check()
}

func (e *Validator) mixedStageInputs(context MixedBackendStagesContext) (*mixedStages, error) {
	binding, err := e.backendDocument(termMixedBackendExecutionBindingV1, context.MixedStageBinding())
	if err != nil {
		return nil, err
	}
	request, err := e.backendDocument(termBackendOperationRequestV1, context.OperationRequest())
	if err != nil {
		return nil, err
	}
	if err = mixedBackendRequest(binding, request); err != nil {
		return nil, err
	}
	responses, err := e.backendDocuments(termBackendOperationResponseV1, context.OperationResponses(), 1024)
	if err != nil {
		return nil, err
	}
	controls, err := e.backendDocuments(termBackendOperationControlV1, context.OperationControls(), 256)
	if err != nil {
		return nil, err
	}
	history, err := backendTranscript(request, responses, controls)
	if err != nil {
		return nil, err
	}
	reports, err := e.backendDocuments(termMixedBackendStageReportV1, context.MixedStageReports(), 64)
	if err != nil {
		return nil, err
	}
	s := &mixedStages{subject: at(binding, "subject"), request: request, history: history, reports: reports, responses: responses, seen: map[string]any{}}
	if err = e.mixedStageTrusted(binding, s, context.MixedStageSnapshot()); err != nil {
		return nil, err
	}
	return s, nil
}
