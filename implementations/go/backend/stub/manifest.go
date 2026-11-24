// Package stub supplies portable in-memory backend doubles without native effects.
package stub

import (
	"encoding/json"
	"io/fs"
	"slices"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/backend"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// Options controls independent advertised roles; its zero value disables optional roles.
type Options struct{ WithOrchestrator, WithEvaluator, WithParticipantRuntime, WithTime, WithObservation, WithRealizationEnvelope bool }

var schemas = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Only immutable packaged contracts are shared; request state remains local.
var packaged = sync.OnceValues(corpus.Open)  //nolint:gochecknoglobals // Only immutable packaged contracts are shared; request state remains local.

// DefaultOptions returns manifest defaults, distinct from runtime target defaults.
func DefaultOptions() Options {
	return Options{WithOrchestrator: true, WithEvaluator: true, WithParticipantRuntime: true, WithObservation: true}
}

// Manifest builds the portable declaration using the reference's unknown-version fallback.
func Manifest(options Options) (backend.Manifest, error) {
	return ManifestWithVersion(options, "0.0.0+unknown")
}

// ManifestWithVersion builds a checked declaration with an explicit apparatus version.
func ManifestWithVersion(options Options, version string) (backend.Manifest, error) {
	owner, err := schemas()
	if err != nil {
		return backend.Manifest{}, err
	}
	document, err := packagedDocument("fixtures/backend-manifest/backend-manifest-v2/valid/stub.json")
	if err != nil {
		return backend.Manifest{}, err
	}
	object(document, "identity")["version"] = version
	contracts := manifestRoles(document, options)
	manifestBindings(document, options)
	if options.WithTime {
		contracts = append(contracts, "time-model-v1", "time-runtime-state-v1", "realized-time-model-v1")
	}
	if options.WithRealizationEnvelope {
		if err := manifestEnvelope(document); err != nil {
			return backend.Manifest{}, err
		}
		contracts = append(contracts, "realization-envelope-v1")
	}
	document["supported_contract_versions"] = contracts
	return normalizeManifest(owner, document)
}

func invalid() error { return fault.New(fault.InvalidInput, "stub-input-invalid", nil) }
func object(input map[string]any, key string) map[string]any {
	result, _ := input[key].(map[string]any)
	return result
}
func stringList(input any) []string {
	rows, _ := input.([]any)
	result := make([]string, 0, len(rows))
	for _, row := range rows {
		if text, ok := row.(string); ok {
			result = append(result, text)
		}
	}
	return result
}
func removeStrings(input, removed []string) []string {
	return slices.DeleteFunc(input, func(item string) bool { return slices.Contains(removed, item) })
}
func packagedDocument(name string) (map[string]any, error) {
	source, err := packaged()
	if err != nil {
		return nil, err
	}
	raw, err := fs.ReadFile(source, name)
	if err != nil {
		return nil, fault.New(fault.Operational, "stub-corpus-invalid", nil)
	}
	document, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, fault.New(fault.Operational, "stub-corpus-invalid", nil)
	}
	result, ok := document.(map[string]any)
	if !ok {
		return nil, invalid()
	}
	return result, nil
}

func manifestRoles(document map[string]any, options Options) []string {
	capabilities := object(document, "capabilities")
	for _, role := range []struct {
		name    string
		enabled bool
	}{{"orchestrator", options.WithOrchestrator}, {"evaluator", options.WithEvaluator}, {"participant_runtime", options.WithParticipantRuntime}, {"observation", options.WithObservation}} {
		if !role.enabled {
			delete(capabilities, role.name)
		}
	}
	contracts := stringList(document["supported_contract_versions"])
	if !options.WithParticipantRuntime {
		contracts = removeStrings(contracts, []string{"participant-episode-state-envelope-v1", "participant-episode-history-event-stream-v1", "participant-behavior-history-event-stream-v1", "participant-lifecycle-event-v1", "participant-observation-envelope-v1", "participant-shared-state-record-v1", "participant-joint-action-record-v1", "participant-time-management-context-v1", "participant-outcome-report-v1"})
	}
	if !options.WithObservation {
		contracts = removeStrings(contracts, []string{"experiment-capture-spec-v1", "experiment-evidence-record-v1", "experiment-derived-measure-v1"})
	}

	return contracts
}
func manifestBindings(document map[string]any, options Options) {
	bindings, _ := document["concept_bindings"].([]any)
	filtered := make([]any, 0, len(bindings)+5)
	for _, binding := range bindings {
		item, _ := binding.(map[string]any)
		scope, _ := item["scope"].(string)
		if (!options.WithParticipantRuntime && strings.HasPrefix(scope, "capabilities.participant_runtime.")) || (!options.WithObservation && strings.HasPrefix(scope, "capabilities.observation.")) {
			continue
		}
		filtered = append(filtered, binding)
	}
	if options.WithTime {
		object(document, "capabilities")["time"] = timeCapabilities(options.WithParticipantRuntime)
		for _, field := range []string{"supported_domain_kinds", "supported_authority_kinds", "supported_advancement_modes", "supported_synchronization_modes", "supported_constraint_kinds"} {
			filtered = append(filtered, map[string]any{"scope": "capabilities.time." + field, "family": "time-and-apparatus"})
		}
	}
	document["concept_bindings"] = filtered
}
func manifestEnvelope(document map[string]any) error {
	owner, err := schemas()
	if err != nil {
		return err
	}
	envelope, err := packagedDocument("realization-envelopes/reference-emulation/in-process-v1.json")
	if err != nil {
		return err
	}
	raw, err := json.Marshal(envelope)
	if err != nil || owner.CheckPortable("realization-envelope-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return invalid()
	}
	document["realization_envelope"] = map[string]any{"contract_id": envelope["contract_id"], "envelope_id": envelope["id"], "schema_version": envelope["schema_version"], "digest": envelope["digest"], termConfigurationDigest: object(envelope, "configuration")[termConfigurationDigest]}
	supports := array(document["realization_support"])
	if len(supports) == 0 {
		return invalid()
	}
	support, ok := supports[0].(map[string]any)
	if !ok {
		return invalid()
	}
	support["supported_constraint_kinds"] = append(stringList(support["supported_constraint_kinds"]), "compute-substrate")
	support["observation_capabilities"] = map[string]any{"compute-substrate": map[string]any{"verification_scope": "presence", "observation_strength": "driver-reported"}}
	return nil
}
func normalizeManifest(owner *admission.Validator, document map[string]any) (backend.Manifest, error) {
	raw, err := json.Marshal(document)
	if err != nil {
		return backend.Manifest{}, invalid()
	}
	var result backend.Manifest
	if json.Unmarshal(raw, &result) != nil {
		return backend.Manifest{}, invalid()
	}
	normalized, err := admission.NormalizeBackendManifest(owner, result)
	if err != nil {
		return backend.Manifest{}, err
	}
	raw, err = json.Marshal(normalized)
	if err != nil || json.Unmarshal(raw, &document) != nil {
		return backend.Manifest{}, invalid()
	}
	if document["realization_envelope"] == nil {
		delete(document, "realization_envelope")
	}
	capabilities := object(document, "capabilities")
	for _, key := range []string{"time", "recovery_observation"} {
		if capabilities[key] == nil {
			delete(capabilities, key)
		}
	}
	raw, err = json.Marshal(document)
	if err != nil {
		return backend.Manifest{}, invalid()
	}
	result = backend.Manifest{}
	if json.Unmarshal(raw, &result) != nil {
		return backend.Manifest{}, invalid()
	}
	return result, nil
}
