package realization

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const runtimeValueCommitment = "raes-runtime-value-jcs-sha256-v1:sha256:"

var realizationOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // The packaged native owner is immutable and holds no request state.

func invalidRealization() error {
	return fault.New(fault.InvalidInput, "processor-realization-invalid", nil)
}

// ProjectConcern returns the safe comparison view of an exact native value.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ProjectConcern(kind string, value admission.Fragment, observed, recursive bool) (admission.Fragment, error) {
	if admission.CheckFragment(value, admission.RealizationValue) != nil {
		return nil, invalidRealization()
	}
	definition, known := concernDefinitionFor(kind)
	if !known {
		return nil, invalidRealization()
	}
	input := value.Document()
	if observed {
		if err := validateObservedConcern(kind, input); err != nil {
			return nil, err
		}
	}
	output, err := projectConcernValue(definition, input, observed, recursive)
	if err != nil {
		return nil, err
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.RealizationValue, output, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}

func validateObservedConcern(kind string, input any) error {
	switch kind {
	case termRuntimeEnvironment:
		return validateEnvironmentObservation(input)
	case termRuntimeMounts:
		return validateMountObservation(input)
	case termPublishedPorts, termLinuxCapabilities:
		_, err := normalizeConcernValue(kind, input)
		return err
	case termForwardingAgents:
		return validateForwardingObservation(input)
	default:
		return nil
	}
}
func projectConcernValue(definition concernDefinition, input any, observed, recursive bool) (any, error) {
	switch definition.kind {
	case termRuntimeEnvironment:
		return projectEnvironment(input, observed, recursive)
	case termRuntimeMounts:
		return projectMounts(input, false, recursive)
	case termPublishedPorts:
		return projectPorts(input, recursive)
	case termLinuxCapabilities:
		return projectCapabilities(input, recursive)
	case termProcessResourceLimits:
		return projectProcessLimits(input, observed, recursive)
	case termForwardingAgents:
		return projectForwarding(input, observed, recursive)
	case termServiceListeners:
		return projectListeners(input, recursive)
	default:
		if len(definition.authored) > 0 && definition.authored[0] == termRuntime {
			return projectTypedRuntime(definition.kind, input, observed, recursive)
		}
		return input, nil
	}
}

func normalizeConcernValue(kind string, value any) (any, error) {
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return nil, err
	}
	descriptor, present := nativeConcernDescriptor(kind)
	if !present {
		return nil, invalidRealization()
	}
	normalized, err := sdl.NormalizeConcernValue(descriptor.Document, fragment)
	if err != nil {
		return nil, err
	}
	return normalized.Document(), nil
}

func validateEnvironmentObservation(value any) error {
	items, ok := value.([]any)
	if !ok {
		return invalidRealization()
	}
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return invalidRealization()
		}
		base := []string{termName, termValueClassification, termProvenance, termSource}
		if _, supplied := record["value_from"]; supplied {
			base = append(base, "value_from")
		}
		candidate, err := restoreCommittedRecord(record, base, termValueClassification)
		if err != nil {
			return err
		}
		if _, err := normalizeConcernValue(termRuntimeEnvironment, []any{candidate}); err != nil {
			return err
		}
	}
	return nil
}

func fieldDefault(record map[string]any, key string, fallback any) any {
	if value, present := record[key]; present {
		return value
	}
	return fallback
}
func emptySensitive(value any) bool {
	if value == nil {
		return true
	}
	text, ok := value.(string)
	return ok && text == ""
}
func protectedClassification(value any) (bool, error) {
	switch value.(type) {
	case map[string]any, []any:
		return false, invalidRealization()
	}
	text, _ := value.(string)
	return text == "redacted" || text == "operator_secret", nil
}
func validCommitment(value any) bool {
	text, ok := value.(string)
	if !ok || !strings.HasPrefix(text, runtimeValueCommitment) {
		return false
	}
	text = strings.TrimPrefix(text, runtimeValueCommitment)
	if len(text) != 64 {
		return false
	}
	for _, char := range text {
		if (char < '0' || char > '9') && (char < 'a' || char > 'f') {
			return false
		}
	}
	return true
}
func valueCommitment(kind, identity string, value any) (string, error) {
	raw, err := json.Marshal(map[string]any{termDomain: "raes.runtime.realization-concern-value", termVersion: 1, "concern_kind": kind, "identity": identity, termValue: value})
	if err != nil {
		return "", invalidRealization()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", invalidRealization()
	}
	return strings.TrimSuffix(runtimeValueCommitment, "sha256:") + digest.SHA256(canonical), nil
}

func committedValue(record map[string]any, kind, identity, classificationField string, observed bool) (map[string]any, error) {
	classification := fieldDefault(record, classificationField, "")
	protected, err := protectedClassification(classification)
	if err != nil {
		return nil, err
	}
	raw := fieldDefault(record, termValue, "")
	if (protected || observed && classification == "secret_fixture") && !emptySensitive(raw) {
		return nil, invalidRealization()
	}
	if commitment := record[termValueCommitment]; commitment != nil {
		if !emptySensitive(raw) || !validCommitment(commitment) {
			return nil, invalidRealization()
		}
		return map[string]any{termValuePresent: true, termValueCommitment: commitment}, nil
	}
	if emptySensitive(raw) {
		return map[string]any{termValuePresent: protected}, nil
	}
	commitment, err := valueCommitment(kind, identity, raw)
	if err != nil {
		return nil, err
	}
	return map[string]any{termValuePresent: true, termValueCommitment: commitment}, nil
}

func projectEnvironment(value any, observed, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	output := make([]any, 0, len(items))
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		name, ok := record[termName].(string)
		if !ok || name == "" {
			return nil, invalidRealization()
		}
		entry := map[string]any{termName: name, termValueClassification: fieldDefault(record, termValueClassification, termUnknown), termProvenance: fieldDefault(record, termProvenance, termUnknown), termSource: fieldDefault(record, termSource, "")}
		if err := projectEnvironmentSource(entry, record); err != nil {
			return nil, err
		}

		commitment, err := committedValue(record, termRuntimeEnvironment, name, termValueClassification, observed)
		if err != nil {
			return nil, err
		}
		maps.Copy(entry, commitment)
		output = append(output, entry)
	}
	if !recursive {
		slices.SortStableFunc(output, func(a, b any) int {
			return strings.Compare(ownedProjection[string](ownedProjection[map[string]any](a)[termName]), ownedProjection[string](ownedProjection[map[string]any](b)[termName]))
		})
	}
	return output, nil
}

func projectEnvironmentSource(entry, record map[string]any) error {
	source := record["value_from"]
	if source == nil {
		return nil
	}
	owner, err := realizationOwner()
	if err != nil {
		return err
	}
	raw, err := json.Marshal(source)
	if err != nil || owner.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/GeneratedArtifactValueSource", raw, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}) != nil {
		return invalidRealization()
	}
	entry["value_from"] = source
	return nil
}
