package admission

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func (e *Validator) materializationCompile(owner MaterializationCompiler, request MaterializationCompileRequest) (*materializationCompiled, error) {
	if len(request.Source) == 0 || len(request.Source) > value.MaterializationBytes || request.ContractID != termMaterializedScenarioV1 && request.ContractID != termInstantiatedScenarioV1 {
		return nil, invalid()
	}
	commitment := digest.SHA256(request.Source)
	predecessorCommitment := digest.SHA256(request.Predecessor)
	request.Source = slices.Clone(request.Source)
	request.Predecessor = slices.Clone(request.Predecessor)
	compiled, err := owner.CompileMaterialization(request)
	if err != nil {
		return nil, invalid()
	}
	if compiled.SourceSHA256 != commitment || digest.SHA256(request.Source) != commitment || digest.SHA256(request.Predecessor) != predecessorCommitment || len(compiled.Resources) > 16384 || len(compiled.CollectionIdentities) > 16384 || len(compiled.RealizationRequirements) > 16384 {
		return nil, invalid()
	}
	result := &materializationCompiled{resources: map[string]any{}, identities: compiled.CollectionIdentities}
	result.document, err = e.materializationModelDocument(request.ContractID, compiled.Document)
	if err != nil {
		return nil, err
	}
	result.full, err = e.materializationModelDocument(request.ContractID, compiled.FullDocument)
	if err != nil {
		return nil, err
	}
	if !materializationSupplied(result.document, result.full) {
		return nil, invalid()
	}
	if err = value.Validate(result.full, value.Runtime()); err != nil {
		return nil, invalid()
	}
	if err = e.materializationResources(result, compiled.Resources); err != nil {
		return nil, err
	}
	if err = materializationIdentityProfiles(compiled.CollectionIdentities); err != nil {
		return nil, err
	}
	result.requirements, err = materializationRequirements(compiled.RealizationRequirements)
	if err != nil {
		return nil, err
	}
	if err = e.materializationPhaseMetadata(result, compiled); err != nil {
		return nil, err
	}
	return result, nil
}

// SDL semantic admission belongs to the compiler owner. Do not recursively run
// materialization execution-context rules on its phase data while checking an
// archive: those rules require a plan and cannot establish the archive's bytes.
func (e *Validator) materializationModelDocument(id string, data []byte) (any, error) {
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err := e.checkModels(id, data, limits); err != nil {
		return nil, err
	}
	return ingress.Parse(data, limits, ingress.Object)
}

func materializationIdentityProfiles(profiles map[string][]string) error {
	remaining := 8 * 1048576
	for path, fields := range profiles {
		if len(path) > 4096 || len(path) > remaining || path != "" && path[0] != '/' || len(fields) == 0 || !flowUniqueReferences(fields) {
			return invalid()
		}
		remaining -= len(path)
		if len(fields) > 8 {
			return invalid()
		}
		for _, field := range fields {
			remaining -= len(field)
		}
		if remaining < 0 {
			return invalid()
		}
		if jsonpointer.FromTokens(jsonpointer.Tokens(path)) != path {
			return invalid()
		}
	}
	return nil
}

func materializationRequirements(raw [][]byte) ([]json.RawMessage, error) {
	result := make([]json.RawMessage, 0, len(raw))
	remaining := 64 * 1048576
	for _, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		if _, err := ingress.Parse(data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object); err != nil {
			return nil, err
		}
		result = append(result, append(json.RawMessage(nil), data...))
	}
	return result, nil
}

func materializationSupplied(supplied, full any) bool {
	if fields, ok := supplied.(map[string]any); ok {
		for key, child := range fields {
			other, present := object(full)[key]
			if !present || !materializationSupplied(child, other) {
				return false
			}
		}
		return object(full) != nil
	}
	if items, ok := supplied.([]any); ok {
		return materializationSuppliedSequence(items, full)
	}
	return equal(supplied, full)
}

func (e *Validator) materializationResources(result *materializationCompiled, resources [][]byte) error {
	remaining := 64 * 1048576
	for _, raw := range resources {
		if len(raw) > remaining {
			return invalid()
		}
		remaining -= len(raw)
		resource, err := e.low.DefaultedObjectFragment(termRuntimeSnapshotV1, "#/$defs/SnapshotEntryModel", raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
		if err != nil {
			return err
		}
		address := stringAt(resource, "address")
		if result.resources[address] != nil || stringAt(resource, "status") != termReady {
			return invalid()
		}
		result.resources[address] = resource
	}
	return nil
}

func materializationSuppliedSequence(items []any, full any) bool {
	other, ok := full.([]any)
	if !ok || len(items) != len(other) {
		return false
	}
	for index, child := range items {
		if !materializationSupplied(child, other[index]) {
			return false
		}
	}
	return true
}
