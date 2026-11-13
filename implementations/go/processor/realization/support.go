package realization

import (
	"fmt"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
)

const (
	termOpenRealization = "open-realization"
	termOperatingSystem = "operating-system"
)

type observationCapability struct{ scope, strength string }
type supportDeclaration struct {
	mode               string
	exact, constraints []string
	observations       map[string]observationCapability
	processLimits      []processCapability
	artifacts          []artifactCapability
}

func declaredSupport(manifest binding.BackendManifestV2, domain string) ([]supportDeclaration, error) {
	result := []supportDeclaration{}
	for _, entry := range sourceValue(manifest.RealizationSupport) {
		if sourceValue(entry.Domain) != domain {
			continue
		}
		declaration := supportDeclaration{mode: string(sourceValue(entry.SupportMode)), exact: sourceValue(entry.SupportedExactRequirementKinds), constraints: sourceValue(entry.SupportedConstraintKinds), observations: map[string]observationCapability{}, processLimits: []processCapability{}}
		for kind, capability := range sourceValue(entry.ObservationCapabilities) {
			declaration.observations[kind] = observationCapability{string(sourceValue(capability.VerificationScope)), string(sourceValue(capability.ObservationStrength))}
		}
		for _, capability := range sourceValue(entry.ProcessResourceLimits) {
			decoded, err := decodeProcessCapability(capability)
			if err != nil {
				return nil, err
			}
			declaration.processLimits = append(declaration.processLimits, decoded)
		}
		for _, capability := range sourceValue(entry.ArtifactMechanisms) {
			decoded, err := decodeArtifactCapability(capability)
			if err != nil {
				return nil, err
			}
			declaration.artifacts = append(declaration.artifacts, decoded)
		}

		result = append(result, declaration)
	}
	return result, nil
}

func supportFinding(requirement Requirement, code, message string) *diagnostic.Diagnostic {
	return &diagnostic.Diagnostic{Code: code, Domain: requirement.Domain, Address: requirement.Address, Message: message, Severity: "error"}
}

func supportDiagnostic(requirement Requirement, options ResolveOptions) (*diagnostic.Diagnostic, error) {
	versioned, installed := versionRequirements(requirement)
	if !installed {
		return supportFinding(requirement, "realization.unsupported-version-relation", "Required version comparison semantics are not installed."), nil
	}
	declarations, err := declaredSupport(options.Manifest, requirement.Domain)
	if err != nil {
		return nil, err
	}
	if versioned {
		if finding := constraintSupportDiagnostic(requirement, declarations); finding != nil {
			return finding, nil
		}
	}
	if requirement.Kind == termProcessResourceLimits {
		return processSupportDiagnostic(requirement, declarations, options.Envelope)
	}
	if structuredRequirement(requirement) {
		if finding := exactSupportDiagnostic(requirement, declarations); finding != nil {
			return finding, nil
		}
	}
	if requirement.Posture == nil {
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
	switch *requirement.Posture {
	case termOpen:
		return openSupportDiagnostic(requirement, declarations), nil
	case termExact:
		return exactSupportDiagnostic(requirement, declarations), nil
	case termConstrained:
		return constraintSupportDiagnostic(requirement, declarations), nil
	default:
		return nil, nil //nolint:nilnil // Absence is a valid optional result in this declared relation.
	}
}

func structuredRequirement(requirement Requirement) bool {
	if requirement.Structure != nil {
		document := ownedProjection[map[string]any](requirement.Structure.Document())
		if document[termKind] == "collection" || document[termKind] == "record" {
			return true
		}
	}
	if requirement.Constraint != nil {
		root := ownedProjection[map[string]any](ownedProjection[map[string]any](requirement.Constraint.Document())["root"])
		return slices.Contains([]string{termRecursiveRecord, termKeyedCollection, termSequence}, ownedProjection[string](root[termKind]))
	}
	return false
}

func observationKind(kind string) string {
	if slices.Contains([]string{termOsFamily, termOsDistribution, termOsVersion}, kind) {
		return termOperatingSystem
	}
	return kind
}
func sufficientlyObserved(requirement Requirement, declarations []supportDeclaration) bool {
	for _, declaration := range declarations {
		capability, present := declaration.observations[observationKind(requirement.Kind)]
		if present && observationSatisfied(capability.scope, capability.strength, requirement.ObservationScope, requirement.ObservationStrength) {
			return true
		}
	}
	return false
}
func underObserved(requirement Requirement, posture string) *diagnostic.Diagnostic {
	return supportFinding(requirement, "realization.under-observed-"+posture+"-requirement", fmt.Sprintf("Backend declares no '%s' corroboration for %s '%s' requirement at '%s' in domain '%s'.", requirement.ObservationScope, posture, requirement.Kind, requirement.FieldPath, requirement.Domain))
}

func exactSupportDiagnostic(requirement Requirement, declarations []supportDeclaration) *diagnostic.Diagnostic {
	definition, registered := concernDefinitionFor(requirement.Kind)
	specific := registered && len(definition.authored) > 0 && definition.authored[0] == termRuntime && requirement.Kind != termProcessResourceLimits
	supporting := []supportDeclaration{}
	for _, declaration := range declarations {
		if slices.Contains(declaration.exact, "declared-capability-match") && (!specific || slices.Contains(declaration.exact, requirement.Kind)) {
			supporting = append(supporting, declaration)
		}
	}
	if len(supporting) == 0 {
		return supportFinding(requirement, "realization.unsupported-exact-requirement", fmt.Sprintf("Backend declares no generic and concern-specific exact realization support ('declared-capability-match') for exact '%s' requirement at '%s' in domain '%s'.", requirement.Kind, requirement.FieldPath, requirement.Domain))
	}
	if requirement.ObservationScope != "" && !sufficientlyObserved(requirement, supporting) {
		return underObserved(requirement, termExact)
	}
	return nil
}

func constraintSupportDiagnostic(requirement Requirement, declarations []supportDeclaration) *diagnostic.Diagnostic {
	supporting := []supportDeclaration{}
	for _, declaration := range declarations {
		if slices.Contains(declaration.constraints, requirement.Kind) {
			supporting = append(supporting, declaration)
		}
	}
	if len(supporting) == 0 {
		return supportFinding(requirement, "realization.unsupported-constraint-requirement", fmt.Sprintf("Backend declares no constraint realization support for constraint kind '%s' at '%s' in domain '%s'.", requirement.Kind, requirement.FieldPath, requirement.Domain))
	}
	if requirement.ObservationScope != "" && !sufficientlyObserved(requirement, supporting) {
		return underObserved(requirement, "constraint")
	}
	return nil
}

func openSupportDiagnostic(requirement Requirement, declarations []supportDeclaration) *diagnostic.Diagnostic {
	if requirement.Kind == termComputeSubstrate {
		return nil
	}
	supporting := []supportDeclaration{}
	for _, declaration := range declarations {
		if declaration.mode == termOpenRealization {
			supporting = append(supporting, declaration)
		}
	}
	if len(supporting) == 0 {
		return supportFinding(requirement, "realization.unsupported-open-requirement", fmt.Sprintf("Backend declares no open realization support for '%s' requirement at '%s' in domain '%s'.", requirement.Kind, requirement.FieldPath, requirement.Domain))
	}
	if requirement.ObservationScope != "" && (requirement.Structure != nil || requirement.Constraint != nil) && !sufficientlyObserved(requirement, supporting) {
		return underObserved(requirement, termOpen)
	}
	return nil
}

func versionRequirements(requirement Requirement) (bool, bool) {
	if requirement.Constraint == nil {
		return false, true
	}
	document := ownedProjection[map[string]any](requirement.Constraint.Document())
	pending := []any{document["root"]}
	definitions, _ := document["definitions"].(map[string]any)
	for _, definition := range definitions {
		pending = append(pending, definition)
	}
	found := false
	for len(pending) > 0 {
		last := len(pending) - 1
		node := ownedProjection[map[string]any](pending[last])
		pending = pending[:last]
		pending = appendVersionConstraintChildren(pending, node)
		if node[termKind] != termDomain {
			continue
		}
		domain := ownedProjection[map[string]any](node[termDomain])
		if domain[termKind] != termVersion {
			continue
		}
		found = true
		relation := ownedProjection[map[string]any](domain["relation"])
		identity := softwareversion.Relation{Authority: ownedProjection[string](relation["authority"]), ID: ownedProjection[string](relation["contract_id"]), Revision: ownedProjection[string](relation["revision"]), Digest: ownedProjection[string](relation["digest"])}
		installed, err := softwareversion.Installed(identity.ID)
		if err != nil || installed != identity {
			return true, false
		}
	}
	return found, true
}

func appendVersionConstraintChildren(pending []any, node map[string]any) []any {
	switch node[termKind] {
	case termRecursiveRecord:
		for _, child := range ownedProjection[map[string]any](node["fields"]) {
			pending = append(pending, child)
		}
	case termSequence:
		pending = append(pending, ownedProjection[[]any](node["items"])...)
	case termKeyedCollection:
		for _, member := range ownedProjection[[]any](node["members"]) {
			pending = append(pending, ownedProjection[map[string]any](member)["constraint"])
		}
	case "all-of":
		pending = append(pending, ownedProjection[[]any](node["constraints"])...)
	}
	return pending
}
