package planning

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func plannedEnvelopeMemberDiagnostics(model processor.CompiledScenario, requirements []realization.Requirement, manifest binding.BackendManifestV2, envelope *binding.RealizationEnvelopeV1) ([]diagnostic.Diagnostic, error) {
	if envelope == nil {
		return nil, nil
	}
	instance, concrete := model.Original.(sdl.InstantiatedScenario)
	if !concrete {
		return nil, nil
	}
	findings, err := sdl.EnvelopeMembershipDiagnostics(instance, *envelope)
	if err != nil || !slices.Contains(fieldValue(manifest.SupportedContractVersions), preparationContract) {
		return findings, err
	}
	paths := []string{}
	for _, requirement := range requirements {
		if requirement.Posture != nil && (*requirement.Posture == "open" || *requirement.Posture == "constrained") {
			paths = append(paths, requirement.FieldPath)
		}
	}
	return preparationMemberDiagnostics(findings, paths), nil
}

func preparationMemberDiagnostics(findings []diagnostic.Diagnostic, paths []string) []diagnostic.Diagnostic {
	kept := make([]diagnostic.Diagnostic, 0, len(findings))
	for _, finding := range findings {
		if preparationChoiceFinding(finding, paths) {
			continue
		}
		kept = append(kept, finding)
	}
	return kept
}

func preparationChoiceFinding(finding diagnostic.Diagnostic, paths []string) bool {
	if finding.Code != "realization-envelope.membership.path-absent" && finding.Code != "realization-envelope.membership.domain-mismatch" {
		return false
	}
	for _, path := range paths {
		if finding.Address == path || strings.HasPrefix(finding.Address, path+".") || strings.HasPrefix(finding.Address, path+"[") {
			return true
		}
	}
	return false
}
