package trial

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func envelopeIdentity(value validation.Value) (json.RawMessage, binding.RealizationEnvelopeV1, error) {
	var result binding.RealizationEnvelopeV1
	var source struct {
		ID            string `json:"id"`
		Contract      string `json:"contract_id"`
		Version       string `json:"schema_version"`
		Digest        string `json:"digest"`
		Configuration struct {
			Digest string `json:"configuration_digest"`
		} `json:"configuration"`
	}
	if value.ContractID() != "realization-envelope-v1" || decode(value.JSON(), &source) != nil {
		return nil, result, trialInvalid()
	}
	owner, err := trialOwner()
	if err != nil {
		return nil, result, err
	}
	if _, err = owner.Validate("realization-envelope-v1", value.JSON(), trialIngress(), nil); err != nil {
		return nil, result, err
	}
	if decode(value.JSON(), &result) != nil {
		return nil, result, trialInvalid()
	}
	raw, err := encoded(struct {
		ID            string `json:"envelope_id"`
		Contract      string `json:"contract_id"`
		Version       string `json:"schema_version"`
		Digest        string `json:"digest"`
		Configuration string `json:"configuration_digest"`
	}{source.ID, source.Contract, source.Version, source.Digest, source.Configuration.Digest})
	return raw, result, err
}
func admitMixedComponents(request Request, input compilationInputs, profile mixedProfile, authority *mixedAuthority) error {
	selected := map[ApparatusManifestKey]manifestMetadata{}
	refs := []reference{}
	capabilities := map[string]bool{}
	for _, id := range slices.Sorted(maps.Keys(profile.Components)) {
		component := profile.Components[id]
		ref := component.Manifest
		key, err := apparatusReferenceKey(ref)
		if err != nil {
			return err
		}
		admitted, err := resolveApparatusReference(request, input, key, ref, "composition component manifest reference has no exact concrete payload")
		if err != nil {
			return err
		}
		metadata, backend, manifest := admitted.metadata, admitted.backend, admitted.manifest

		identity, carrier, err := mixedComponentEnvelope(request, component.Envelope)
		if err != nil {
			return err
		}
		if backend != nil && !sameJSON(metadata.Envelope, identity) {
			return refuse("apparatus-envelope-unsupported", pathRealizationEnvelope, "composition backend manifest does not bind its selected realization envelope")
		}
		selected[key] = metadata
		refs = append(refs, ref)
		authority.manifests[key] = manifest
		if backend != nil {
			authority.backends[key] = *backend
			authority.envelopes[key] = carrier
		}
		addManifestCapabilities(capabilities, key, metadata)
	}
	if err := selectedCompatibility(selected, true); err != nil {
		return err
	}
	return validateApparatusIntent(input.spec.ApparatusIntent, selected, refs, capabilities, true)
}
func mixedComponentEnvelope(request Request, reference json.RawMessage) (json.RawMessage, binding.RealizationEnvelopeV1, error) {
	var coordinate struct {
		ID string `json:"envelope_id"`
	}
	if decode(reference, &coordinate) != nil {
		return nil, binding.RealizationEnvelopeV1{}, trialInvalid()
	}
	envelope, ok := request.MixedRealizationEnvelopes[coordinate.ID]
	if !ok {
		return nil, binding.RealizationEnvelopeV1{}, refuse("apparatus-envelope-identity-mismatch", pathRealizationEnvelope, "composition component realization envelope is unresolved or stale")
	}
	identity, carrier, err := envelopeIdentity(envelope)
	if err != nil {
		return nil, binding.RealizationEnvelopeV1{}, err
	}
	if !sameJSON(identity, reference) {
		return nil, binding.RealizationEnvelopeV1{}, refuse("apparatus-envelope-identity-mismatch", pathRealizationEnvelope, "composition component realization envelope is unresolved or stale")
	}
	return identity, carrier, nil
}
func addManifestCapabilities(result map[string]bool, key ApparatusManifestKey, manifest manifestMetadata) {
	for _, contract := range manifest.Contracts {
		result[contract] = true
	}
	if key.ComponentKind == componentBackend {
		if slices.Contains(manifest.Contracts, "evaluation-result-envelope-v1") {
			result["evaluation-results"] = true
		}
		if slices.Contains(manifest.Contracts, "workflow-result-envelope-v1") {
			result["workflow-results"] = true
		}
		return
	}
	for _, set := range [][]string{manifest.Capabilities.SDL, manifest.Capabilities.Features} {
		for _, feature := range set {
			result[feature] = true
		}
	}
}
func selectedCompatibility(selected map[ApparatusManifestKey]manifestMetadata, mixed bool) error {
	backends := []manifestMetadata{}
	for key, manifest := range selected {
		if key.ComponentKind == componentBackend {
			backends = append(backends, manifest)
		}
	}
	for _, key := range sortedApparatusKeys(selected) {
		if key.ComponentKind != componentProcessor {
			continue
		}
		if err := processorCompatibility(selected[key], backends, mixed); err != nil {
			return err
		}
	}
	return nil
}
func processorCompatibility(processor manifestMetadata, backends []manifestMetadata, mixed bool) error {
	matched := len(backends) == 0
	for _, backend := range backends {
		compatible := slices.Contains(processor.Compatibility.Backends, backend.Identity.Name) && slices.Contains(backend.Compatibility.Processors, processor.Identity.Name)
		matched = matched || compatible
		if !mixed && !compatible {
			return refuse("apparatus-compatibility-rejected", pathApparatusManifests, "selected processor and backend manifests are not mutually compatible")
		}
	}
	if !matched {
		return refuse("apparatus-compatibility-rejected", pathApparatusManifests, "composition processor has no mutually compatible selected backend")
	}
	return nil
}
func sortedApparatusKeys[V any](selected map[ApparatusManifestKey]V) []ApparatusManifestKey {
	result := slices.Collect(maps.Keys(selected))
	slices.SortFunc(result, func(a, b ApparatusManifestKey) int {
		for _, pair := range [][2]string{{a.ComponentKind, b.ComponentKind}, {a.ComponentName, b.ComponentName}, {a.ComponentVersion, b.ComponentVersion}, {a.ManifestVersion, b.ManifestVersion}} {
			if pair[0] < pair[1] {
				return -1
			}
			if pair[0] > pair[1] {
				return 1
			}
		}
		return 0
	})
	return result
}

type apparatusIntent struct {
	Capabilities []string    `json:"required_capabilities"`
	Processors   []reference `json:"allowed_processor_refs"`
	Backends     []reference `json:"allowed_backend_refs"`
	Manifests    []reference `json:"required_manifest_refs"`
}

func validateApparatusIntent(raw json.RawMessage, selected map[ApparatusManifestKey]manifestMetadata, refs []reference, capabilities map[string]bool, mixed bool) error {
	if isNull(raw) {
		return nil
	}
	var intent apparatusIntent
	if decode(raw, &intent) != nil {
		return trialInvalid()
	}
	if err := requiredApparatusCapabilities(intent.Capabilities, capabilities, mixed); err != nil {
		return err
	}
	if err := apparatusKindAllowlist(componentProcessor, selected, intent.Processors); err != nil {
		return err
	}
	if err := apparatusKindAllowlist(componentBackend, selected, intent.Backends); err != nil {
		return err
	}
	return requiredApparatusManifests(refs, intent.Manifests, mixed)
}
func requiredApparatusCapabilities(required []string, available map[string]bool, mixed bool) error {
	for _, capability := range required {
		if !available[capability] {
			message := "selected apparatus does not satisfy every required capability"
			if mixed {
				message = "composition apparatus does not satisfy every required capability"
			}
			return refuse("apparatus-capability-missing", "/apparatus/capability_refs", message)
		}
	}
	return nil
}
func apparatusKindAllowlist(kind string, selected map[ApparatusManifestKey]manifestMetadata, allowed []reference) error {
	if len(allowed) == 0 {
		return nil
	}
	count := 0
	for key, manifest := range selected {
		if key.ComponentKind != kind {
			continue
		}
		count++
		if !apparatusIdentityAllowed(kind, manifest, allowed) {
			return apparatusAllowlistRefusal()
		}
	}
	if count == 0 {
		return apparatusAllowlistRefusal()
	}
	return nil
}
func apparatusAllowlistRefusal() error {
	return refuse("apparatus-identity-not-allowed", pathApparatusManifests, "selected apparatus identity is outside its admitted kind-specific allowlist")
}
func apparatusIdentityAllowed(kind string, manifest manifestMetadata, allowed []reference) bool {
	for _, ref := range allowed {
		if ref.Kind == kind && ref.ID == manifest.Identity.Name && text(ref.Version) == manifest.Identity.Version {
			return true
		}
	}
	return false
}
func requiredApparatusManifests(selected, required []reference, mixed bool) error {
	for _, ref := range required {
		if !selectedManifestSatisfies(selected, ref) {
			message := "selected apparatus does not include every exact required manifest"
			if mixed {
				message = "composition apparatus omits a required manifest"
			}
			return refuse("apparatus-manifest-missing", pathApparatusManifests, message)
		}
	}
	return nil
}
func selectedManifestSatisfies(selected []reference, required reference) bool {
	for _, ref := range selected {
		if manifestReferenceSatisfies(ref, required) {
			return true
		}
	}
	return false
}
func manifestReferenceSatisfies(actual, required reference) bool {
	if actual.Kind != required.Kind || actual.ID != required.ID || required.Version != nil && text(actual.Version) != text(required.Version) || required.Digest != nil && text(actual.Digest) != text(required.Digest) {
		return false
	}
	if required.Subject == nil {
		return true
	}
	if actual.Subject == nil {
		return false
	}
	return actual.Subject.Kind == required.Subject.Kind && actual.Subject.ID == required.Subject.ID && (required.Subject.Version == nil || text(actual.Subject.Version) == text(required.Subject.Version))
}
