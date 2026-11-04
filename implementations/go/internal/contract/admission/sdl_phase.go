package admission

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

// SDLPhaseRequest supplies exact source bytes to the configured native SDL owner.
type SDLPhaseRequest struct {
	ContractID string
	Source     []byte
}

// SDLPhaseAdmission is the owner's admitted supplied-field JSON projection.
// It preserves JSON types and omission, and binds the exact requested source.
// It grants no execution, materialization, archive or inventory authority.
type SDLPhaseAdmission struct {
	ContractID   string
	SourceSHA256 string
	Document     []byte
}

// SDLPhaseOwner admits the complete native model for the requested SDL phase.
// Implementations must derive phase data independently of untrusted candidate
// claims. A callback that merely echoes the request does not implement this port.
type SDLPhaseOwner interface {
	AdmitSDLPhase(request SDLPhaseRequest) (SDLPhaseAdmission, error)
}

func sdlPhaseContract(id string) bool {
	return id == termSdlAuthoringInputV1 || id == termInstantiatedScenarioV1 || id == termMaterializedScenarioV1
}

func (e *Validator) checkSDLPhase(id string, data []byte, limits ingress.Limits, context any) (err error) {
	if !sdlPhaseContract(id) {
		return nil
	}
	defer func() {
		if recover() != nil {
			err = invalid()
		}
	}()
	owner, ok := context.(SDLPhaseOwner)
	if !ok {
		return contextRequired()
	}
	commitment := digest.SHA256(data)
	request := SDLPhaseRequest{ContractID: id, Source: slices.Clone(data)}
	phase, ownerErr := owner.AdmitSDLPhase(request)
	if ownerErr != nil || phase.ContractID != id || phase.SourceSHA256 != commitment || digest.SHA256(request.Source) != commitment {
		return invalid()
	}
	if schemaErr := e.low.CheckSchema(id, phase.Document, limits); schemaErr != nil {
		return invalid()
	}
	source, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return err
	}
	admitted, err := ingress.Parse(phase.Document, limits, ingress.Object)
	if err != nil || !equal(source, admitted) {
		return invalid()
	}
	return nil
}
