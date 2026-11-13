package planning

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const materializationContract = "backend-materialization-attestation-v1"
const descendantsContract = "backend-runtime-descendants-v1"

func materializationRefusal(kind string) diagnostic.Diagnostic {
	code, message := "materialization.source-invalid", "The admitted full source does not satisfy the materialization source contract."
	switch kind {
	case "context":
		code, message = "materialization.source-context-required", "Materialization reporting requires the admitted full source and a safe run identity."
	case "limit":
		code, message = "materialization.source-limit-exceeded", "The admitted full source exceeds the materialization document limit of 4194304 bytes or its portable value bounds."
	}
	return planDiagnostic(code, "materialization", "materialization.source", message)
}

func plannedMaterializationSource(model processor.CompiledScenario, manifest binding.BackendManifestV2, scope *Scope) (json.RawMessage, []diagnostic.Diagnostic, error) {
	versions := fieldValue(manifest.SupportedContractVersions)
	required := model.AugmentationScopeRequired
	reporting := slices.Contains(versions, materializationContract)
	findings := []diagnostic.Diagnostic{}
	if required && (!reporting || !slices.Contains(versions, "backend-augmentation-scope-v1")) {
		findings = append(findings, planDiagnostic("augmentation.scope-unsupported", "augmentation", "/augmentation_scope", "Explicit augmentation permission requires negotiated scope enforcement and materialization reporting."))
	}
	if model.Descriptive || !reporting && !required {
		return nil, findings, nil
	}
	descendants := slices.Contains(versions, descendantsContract)
	if scope == nil || scope.RunID == nil || descendants && (scope.TargetName == nil || *scope.TargetName == "") {
		return nil, append(findings, materializationRefusal("context")), nil
	}
	snapshot, err := sdl.CanonicalBytes(model.Original)
	if err != nil {
		return nil, nil, err
	}
	if !materializationSnapshotWithinLimits(snapshot) {
		return nil, append(findings, materializationRefusal("limit")), nil
	}
	source, refusal, err := sealMaterializationSource(snapshot, scope, descendants)
	if err != nil {
		return nil, nil, err
	}
	if refusal != "" {
		findings = append(findings, materializationRefusal(refusal))
	}
	return source, findings, nil
}

func materializationSnapshotWithinLimits(snapshot []byte) bool {
	if len(snapshot) > value.MaterializationBytes {
		return false
	}
	parsed, err := ingress.Parse(snapshot, ingress.Limits{MaxBytes: value.MaterializationBytes, MaxDepth: 64}, ingress.Object)
	return err == nil && value.Validate(parsed, value.Runtime()) == nil
}

func sealMaterializationSource(snapshot []byte, scope *Scope, descendants bool) (json.RawMessage, string, error) {
	var header struct {
		Scenario struct {
			Provenance struct {
				Authored struct {
					Value string `json:"value"`
				} `json:"authored_digest"`
			} `json:"instantiation_provenance"`
		} `json:"scenario"`
	}
	if json.Unmarshal(snapshot, &header) != nil {
		return nil, "invalid", nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	owner, err := planOwner()
	if err != nil {
		return nil, "", err
	}
	input := map[string]any{
		"contract_id": materializationContract, "snapshot": value.DeclaredDocument(string(snapshot)),
		"authored_digest": header.Scenario.Provenance.Authored.Value, "instantiated_digest": digest.SHA256(snapshot), "run_id": *scope.RunID,
	}
	if descendants {
		input["target_scope"] = "target:" + *scope.TargetName
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	fragment, err := admission.AdmitFragment(owner, admission.MaterializationSourceContext, input, limits)
	if err == nil {
		return rawProjection(fragment.Document()), "", nil
	}
	// Recheck the same bound snapshot with fixed context. A context refusal
	// stays separate from an invalid source, and never exposes either value.
	input["run_id"] = "scope-check"
	delete(input, "target_scope")
	if _, err := admission.AdmitFragment(owner, admission.MaterializationSourceContext, input, limits); err == nil {
		return nil, "context", nil
	}
	return nil, "invalid", nil
}
