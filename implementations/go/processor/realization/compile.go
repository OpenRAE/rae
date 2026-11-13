package realization

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type compiledConcern struct {
	input                    *realizationSource
	definition               concernDefinition
	name, fieldPath, pointer string
	value                    admission.Fragment
}

// Compile lowers one native instantiated scenario through the fixed concern
// registry. Constructor defaults never become author declarations.
func Compile(scenario sdl.InstantiatedScenario) (Resolution, error) {
	input, err := loadRealizationSource(scenario)
	if err != nil {
		return Resolution{}, err
	}
	result := Resolution{Requirements: []Requirement{}, Authority: []Authority{}, Diagnostics: []diagnostic.Diagnostic{}}
	if err := input.compileComputeSubstrate(&result); err != nil {
		return Resolution{}, err
	}
	for _, definition := range concernDefinitions {
		for _, name := range input.sections[definition.section].names {
			requirement, authority, err := input.compileRegisteredConcern(definition, name)
			if err != nil {
				return Resolution{}, err
			}
			if requirement != nil {
				result.Requirements = append(result.Requirements, *requirement)
			}
			if authority != nil {
				result.Authority = append(result.Authority, *authority)
			}
		}
	}
	if err := input.compileOtherRequirements(&result); err != nil {
		return Resolution{}, err
	}
	return result, nil
}

func (s *realizationSource) compileRegisteredConcern(definition concernDefinition, name string) (*Requirement, *Authority, error) {
	fieldPath := definition.section + "." + name + "." + strings.Join(definition.authored, ".")
	pointer := jsonpointer.FromTokens(append([]string{definition.section, name}, definition.authored...))
	value, err := sourceConcernValue(s.sections[definition.section].values[name], definition.authored)
	if err != nil {
		return nil, nil, err
	}
	record := s.semanticRecord(fieldPath, definition.excluded)
	if record != nil && definition.nonStatefulMountsOnly && !containsNonStatefulMount(value) {
		return nil, nil, nil
	}
	address, err := s.resourceAddress(definition.section, name)
	if err != nil {
		return nil, nil, err
	}
	selected, err := s.registeredPosture(record, pointer)
	if err != nil {
		return nil, nil, err
	}
	mode, provenance, source, scope, delegated, posture := selected.mode, selected.provenance, selected.source, selected.scope, selected.delegated, selected.posture
	verification, strength := operationalVerification(definition.kind, value)
	authority := &Authority{Address: address, FieldPath: fieldPath, Concern: definition.kind, Posture: mode, Provenance: provenance, Domain: termRuntimeRealization, Source: source, GoverningScope: scope, PayloadPath: append([]string{}, definition.payload...), ObservationScope: verification, ObservationStrength: strength, Delegated: delegated}
	if posture == nil && !delegated {
		return nil, authority, nil
	}
	requirement := &Requirement{Address: address, FieldPath: fieldPath, Kind: definition.kind, Domain: termRuntimeRealization, GoverningScope: scope, Provenance: provenance, Posture: posture, Delegated: delegated, ObservationScope: verification, ObservationStrength: strength, ValueConstraints: []ValueConstraint{}, ProcessResourceLimits: []ProcessResourceLimit{}}
	if err := s.compileBounds(requirement, pointer, value); err != nil {
		return nil, nil, err
	}
	if record != nil {
		if err := s.compileConcernConstraint(requirement, authority, definition, name, fieldPath, pointer, value); err != nil {
			return nil, nil, err
		}
	}

	return requirement, authority, nil
}

type registeredConcernPosture struct {
	mode, provenance, source, scope string
	delegated                       bool
	posture                         *string
}

func (s *realizationSource) registeredPosture(record *explicitnessRecord, pointer string) (registeredConcernPosture, error) {
	if record != nil {
		source := "authored-leaf"
		if record.Provenance == termProcessorDerived {
			source = termProcessorDerived
		}
		posture := record.Classification
		return registeredConcernPosture{mode: posture, provenance: record.Provenance, source: source, scope: "#" + pointer, posture: &posture}, nil
	}
	mode, provenance, source, scope := termClosed, termAuthorDeclared, termLegacyDefault, ""
	var delegated bool
	var posture *string

	resolved, err := sdl.ResolveRealizationDesignation(s.scenario, pointer)
	if err != nil {
		return registeredConcernPosture{}, err
	}
	designation := ownedProjection[map[string]any](resolved.Document())
	if designation["closure"] == termOpenWorld {
		mode = termOpen
		cloned := mode
		posture = &cloned
	}
	if value, ok := designation[termGoverningScope].(string); ok {
		scope = value
	}
	delegated, _ = designation["delegated"].(bool)
	switch designation[termSource] {
	case termScope:
		source = termAuthoredScope
	case termApparatusDefault:
		source = termApparatusDefault
	}
	return registeredConcernPosture{mode, provenance, source, scope, delegated, posture}, nil
}

func (s *realizationSource) compileConcernConstraint(requirement *Requirement, authority *Authority, definition concernDefinition, name, fieldPath, pointer string, value any) error {
	fragment, err := s.valueFragment(value)
	if err != nil {
		return err
	}
	compiled := &compiledConcern{input: s, definition: definition, name: name, fieldPath: fieldPath, pointer: pointer, value: fragment}
	requirement.source = compiled
	opened, err := compiled.lower(requirement, "")
	if err != nil {
		return err
	}
	if opened && (requirement.Structure != nil || requirement.Constraint != nil) {
		cloned := termOpen
		requirement.Posture = &cloned
		authority.Posture = cloned
	}
	return nil
}

func containsNonStatefulMount(value any) bool {
	items, ok := value.([]any)
	if !ok || len(items) == 0 {
		return true
	}
	for _, item := range items {
		if record, ok := item.(map[string]any); ok && (record["source_kind"] == termBind || record["source_kind"] == termTmpfs) {
			return true
		}
	}
	return false
}

func operationalVerification(kind string, value any) (string, string) {
	switch kind {
	case termOsFamily, termOsDistribution, termOsVersion:
		if text, ok := value.(string); ok && text != "" {
			return termPresence, ""
		}
		return "", ""
	case termForwardingAgents:
		if forwardingConfigured(value) {
			return termConfiguration, ""
		}
		return termPresence, ""

	case termProcessResourceLimits:
		return termConfiguration, "guest-observed"
	case termLinuxCapabilities, termPublishedPorts, termServiceListeners:
		return termConfiguration, ""
	case termRuntimeSoftwareComponents, termRuntimeRepositoryState:
		return "", ""
	default:
		if strings.HasPrefix(kind, "runtime-") {
			return termConfiguration, ""
		}
		return "", ""
	}
}

func forwardingConfigured(value any) bool {
	items, _ := value.([]any)
	for _, item := range items {
		record, _ := item.(map[string]any)
		for _, field := range []string{termSources, termTransforms, termShipTargets, termReloadChannels, "settings"} {
			if values, ok := record[field].([]any); ok && len(values) > 0 {
				return true
			}
		}
		if record["buffer_policy"] != nil {
			return true
		}
	}
	return false
}
