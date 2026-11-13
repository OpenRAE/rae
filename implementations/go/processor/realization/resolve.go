package realization

import (
	"bytes"
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type requirementIdentity struct{ address, path, kind string }

func requirementKey(input Requirement) requirementIdentity {
	return requirementIdentity{input.Address, input.FieldPath, input.Kind}
}
func authorityKey(input Authority) requirementIdentity {
	return requirementIdentity{input.Address, input.FieldPath, input.Concern}
}

// Resolve freezes apparatus decisions and lowers retained source once. The
// result is a pure authority projection, without backend or observation claims.
func Resolve(requirements []Requirement, authority []Authority, options ResolveOptions) (Resolution, error) {
	if max(len(requirements), len(authority), len(options.Decisions)) > 16384 {
		return Resolution{}, invalidRealization()
	}
	if err := checkResolutionTarget(options); err != nil {
		return Resolution{}, err
	}
	known, err := checkResolutionRequirements(requirements, authority)
	if err != nil {
		return Resolution{}, err
	}
	decisions, err := resolutionDecisions(options.Decisions, known)
	if err != nil {
		return Resolution{}, err
	}
	result := Resolution{Requirements: []Requirement{}, Authority: []Authority{}, Diagnostics: []diagnostic.Diagnostic{}}
	opened := map[requirementIdentity]bool{}
	for _, input := range requirements {
		requirement, include, isOpen, resolveErr := resolveRequirement(input, decisions[requirementKey(input)])
		if resolveErr != nil {
			return Resolution{}, resolveErr
		}
		if !include {
			continue
		}
		opened[requirementKey(input)] = isOpen
		result.Requirements = append(result.Requirements, requirement)
	}

	result.Authority, err = resolveAuthority(authority, known, decisions, opened)
	if err != nil {
		return Resolution{}, err
	}

	result.Diagnostics, err = resolutionDiagnostics(result.Requirements, options)
	if err != nil {
		return Resolution{}, err
	}
	return result, nil
}

func resolutionDiagnostics(requirements []Requirement, options ResolveOptions) ([]diagnostic.Diagnostic, error) {
	findings := []diagnostic.Diagnostic{}
	for _, requirement := range requirements {
		finding, err := supportDiagnostic(requirement, options)
		if err != nil {
			return nil, err
		}
		if finding != nil {
			findings = append(findings, *finding)
		}
	}
	envelopeFindings, err := realizationEnvelopeDiagnostics(requirements, options)
	if err != nil {
		return nil, err
	}
	return append(findings, envelopeFindings...), nil
}

func resolveAuthority(authority []Authority, known map[requirementIdentity]bool, decisions map[requirementIdentity]string, opened map[requirementIdentity]bool) ([]Authority, error) {
	result := make([]Authority, 0, len(authority))

	for _, input := range authority {
		entry := input
		entry.PayloadPath = slices.Clone(input.PayloadPath)
		key := authorityKey(entry)
		if entry.Delegated {
			if !known[key] {
				return nil, invalidRealization()
			}
			entry.Posture = termClosed
			if decisions[key] == termOpenWorld {
				entry.Posture = termOpen
			}
			entry.Delegated = false
		}
		if opened[key] {
			entry.Posture = termOpen
		}
		result = append(result, entry)
	}
	return result, nil
}

func checkResolutionRequirements(requirements []Requirement, authority []Authority) (map[requirementIdentity]bool, error) {
	if err := checkRequirementBatch(requirements); err != nil {
		return nil, err
	}
	known := map[requirementIdentity]bool{}
	for _, requirement := range requirements {
		key := requirementKey(requirement)
		if known[key] {
			return nil, invalidRealization()
		}
		known[key] = true
	}
	for _, entry := range authority {
		if err := checkCompiledAuthority(entry); err != nil {
			return nil, err
		}
	}
	return known, nil
}
func resolutionDecisions(input []Decision, known map[requirementIdentity]bool) (map[requirementIdentity]string, error) {
	decisions := map[requirementIdentity]string{}
	for _, decision := range input {
		key := requirementIdentity{decision.Address, decision.FieldPath, decision.Kind}
		if !known[key] || decisions[key] != "" || decision.Closure != termOpenWorld && decision.Closure != "closed-world" {
			return nil, invalidRealization()
		}
		decisions[key] = decision.Closure
	}
	return decisions, nil
}
func resolveRequirement(input Requirement, decision string) (Requirement, bool, bool, error) {
	requirement := copyRequirement(input)
	if decision == "" {
		decision = "closed-world"
	}
	opened, err := lowerPendingRequirement(&requirement, decision)
	if err != nil {
		return Requirement{}, false, false, err
	}
	if input.Delegated {
		if decision != termOpenWorld {
			return Requirement{}, false, false, nil
		}
		posture := termOpen
		requirement.Posture = &posture
		requirement.Delegated = false
	}
	return requirement, true, opened, nil
}
func lowerPendingRequirement(requirement *Requirement, decision string) (bool, error) {
	if !requirement.RecursivePending {
		return false, nil
	}
	if requirement.source == nil || requirement.source.fieldPath != requirement.FieldPath || requirement.source.definition.kind != requirement.Kind {
		requirement.RecursivePending = false
		requirement.StructureError = true
		return false, nil
	}
	isOpen, err := requirement.source.lower(requirement, decision)
	if err != nil {
		return false, err
	}
	if requirement.RecursivePending {
		requirement.RecursivePending = false
		requirement.StructureError = true
	}
	if isOpen {
		posture := termOpen
		requirement.Posture = &posture
	}
	return isOpen, nil
}

func copyRequirement(input Requirement) Requirement {
	result := input
	if input.Posture != nil {
		posture := *input.Posture
		result.Posture = &posture
	}
	result.ValueConstraints = slices.Clone(input.ValueConstraints)
	for i := range result.ValueConstraints {
		result.ValueConstraints[i].Parameter = slices.Clone(input.ValueConstraints[i].Parameter)
	}
	result.ProcessResourceLimits = slices.Clone(input.ProcessResourceLimits)
	if input.ArtifactRequirement != nil {
		encoded, err := json.Marshal(input.ArtifactRequirement)
		if err != nil {
			panic("realization: invalid owned artifact requirement")
		}
		result.ArtifactRequirement = new(*input.ArtifactRequirement)
		if json.Unmarshal(encoded, result.ArtifactRequirement) != nil {
			panic("realization: invalid owned artifact requirement")
		}
	}
	return result
}

func checkCompiledAuthority(input Authority) error {
	if !address.Valid(input.Address) || input.FieldPath == "" || input.Domain == "" || input.Concern == "" || len(input.PayloadPath) == 0 || input.Delegated != (input.Source == termApparatusDefault) {
		return invalidRealization()
	}
	if !slices.Contains([]string{termClosed, termOpen, termExact, termConstrained}, input.Posture) || !slices.Contains([]string{"authored-leaf", termAuthoredScope, termApparatusDefault, termLegacyDefault, termProcessorDerived}, input.Source) || !slices.Contains([]string{termAuthorDeclared, termProcessorDerived, "backend-realized"}, input.Provenance) {
		return invalidRealization()
	}
	if input.Constraint != nil && admission.CheckFragment(input.Constraint, admission.RealizationConstraint) != nil {
		return invalidRealization()
	}
	document := map[string]any{termAddress: input.Address, "field_path": input.FieldPath, termDomain: input.Domain, "requirement_kind": input.Concern, "payload_path": stringValues(input.PayloadPath), "mode": input.Posture, termSource: input.Source, termProvenance: input.Provenance, termGoverningScope: input.GoverningScope, "verification_scope": input.ObservationScope, "required_observation_strength": input.ObservationStrength}
	if value.Validate(document, value.Runtime()) != nil {
		return invalidRealization()
	}
	return nil
}

func checkResolutionTarget(options ResolveOptions) error {
	owner, err := realizationOwner()
	if err != nil {
		return err
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if checkErr := admission.CheckTransport(options.Manifest, limits); checkErr != nil {
		return checkErr
	}
	raw, err := json.Marshal(options.Manifest)
	if err != nil {
		return invalidRealization()
	}
	if checkErr := owner.CheckPortable("backend-manifest-v2", raw, limits); checkErr != nil {
		return checkErr
	}
	identity := sourceValue(options.Manifest.RealizationEnvelope)
	hasIdentity := len(identity) > 0 && !bytes.Equal(identity, []byte("null"))
	if !hasIdentity {
		if options.Envelope != nil {
			return invalidRealization()
		}
		return nil
	}
	if options.Envelope == nil || admission.CheckTransport(options.Envelope, limits) != nil {
		return invalidRealization()
	}
	envelopeRaw, err := json.Marshal(options.Envelope)
	if err != nil {
		return invalidRealization()
	}
	if err := owner.CheckPortable("realization-envelope-v1", envelopeRaw, limits); err != nil {
		return err
	}
	return checkResolutionEnvelopeIdentity(identity, *options.Envelope)
}
func checkResolutionEnvelopeIdentity(identity []byte, envelope binding.RealizationEnvelopeV1) error {
	var declared struct{ ContractID, SchemaVersion, ID, Digest, ConfigurationDigest string }
	var portable struct {
		ContractID          string `json:"contract_id"`
		SchemaVersion       string `json:"schema_version"`
		ID                  string `json:"envelope_id"`
		Digest              string `json:"digest"`
		ConfigurationDigest string `json:"configuration_digest"`
	}
	if json.Unmarshal(identity, &portable) != nil {
		return invalidRealization()
	}
	declared.ContractID, declared.SchemaVersion, declared.ID, declared.Digest, declared.ConfigurationDigest = portable.ContractID, portable.SchemaVersion, portable.ID, portable.Digest, portable.ConfigurationDigest
	if declared.ContractID == "" {
		declared.ContractID = "realization-envelope-v1"
	}
	if declared.SchemaVersion == "" {
		declared.SchemaVersion = "realization-envelope/v1"
	}
	configuration := sourceValue(envelope.Configuration)
	contractID, schemaVersion := sourceValue(envelope.ContractId), sourceValue(envelope.SchemaVersion)
	if contractID == "" {
		contractID = "realization-envelope-v1"
	}
	if schemaVersion == "" {
		schemaVersion = "realization-envelope/v1"
	}
	if declared.ContractID != contractID || declared.SchemaVersion != schemaVersion || declared.ID != sourceValue(envelope.Id) || declared.Digest != sourceValue(envelope.Digest) || declared.ConfigurationDigest != sourceValue(configuration.ConfigurationDigest) {
		return invalidRealization()
	}
	return nil
}
