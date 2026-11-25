package analysis

import (
	"context"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// witnessPhaseOwner supplies only the native closed-phase facts required by
// satisfiability admission. It cannot admit materialization or project nodes.
//
//nolint:containedctx // The synchronous admission callback has no context argument; this request-local adapter carries caller cancellation.
type witnessPhaseOwner struct{ ctx context.Context }

func (o witnessPhaseOwner) CompileMaterialization(request admission.MaterializationCompileRequest) (admission.MaterializationCompilation, error) {
	if request.ContractID != "instantiated-scenario-v1" || request.Plan.ContractID() != "" || len(request.Predecessor) != 0 {
		return admission.MaterializationCompilation{}, invalidAnalysis()
	}
	scenario, err := sdl.ParseWithContext(o.ctx, request.Source, sdl.DefaultParseOptions())
	if err != nil {
		return admission.MaterializationCompilation{}, err
	}
	instance, err := sdl.AdmitInstantiated(scenario)
	if err != nil {
		return admission.MaterializationCompilation{}, err
	}
	document, err := sdl.DocumentBytes(instance)
	if err != nil {
		return admission.MaterializationCompilation{}, err
	}
	full, err := sdl.DocumentBytes(instance)
	if err != nil {
		return admission.MaterializationCompilation{}, err
	}
	return admission.MaterializationCompilation{SourceSHA256: digest.SHA256(request.Source), Document: document, FullDocument: full}, nil
}
func (witnessPhaseOwner) NormalizeMaterializationNode(admission.MaterializationNodeProjection) (json.RawMessage, error) {
	return nil, invalidAnalysis()
}
