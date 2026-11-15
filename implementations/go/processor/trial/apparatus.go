package trial

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type apparatusSelection struct {
	metadata     map[ApparatusManifestKey]manifestMetadata
	backends     map[ApparatusManifestKey]binding.BackendManifestV2
	capabilities map[string]bool
	manifests    map[ApparatusManifestKey]admission.ApparatusManifest
}
type apparatusReference struct {
	manifest admission.ApparatusManifest
	metadata manifestMetadata
	backend  *binding.BackendManifestV2
}

func apparatusReferenceKey(ref reference) (ApparatusManifestKey, error) {
	if ref.Subject == nil || ref.Subject.Version == nil || ref.Version == nil || (ref.Subject.Kind != componentBackend && ref.Subject.Kind != componentProcessor) {
		return ApparatusManifestKey{}, refuse("apparatus-manifest-reference-invalid", pathApparatusManifests, "selected apparatus manifest references require an exact processor or backend subject identity")
	}
	return ApparatusManifestKey{ComponentKind: ref.Subject.Kind, ComponentName: ref.Subject.ID, ComponentVersion: text(ref.Subject.Version), ManifestVersion: text(ref.Version)}, nil
}
func resolveApparatusReference(request Request, input compilationInputs, key ApparatusManifestKey, ref reference, missingMessage string) (apparatusReference, error) {
	var result apparatusReference
	manifest, present := request.ApparatusManifests[key]
	if !present {
		return result, refuse("apparatus-manifest-payload-missing", pathApparatusManifests, missingMessage)
	}
	raw, metadata, backend, err := admitApparatusManifest(input.owner, key, manifest)
	if err != nil {
		return result, err
	}
	if metadata.Identity.Name != ref.ID || metadata.Identity.Name != key.ComponentName || metadata.Identity.Version != key.ComponentVersion || metadata.SchemaVersion != key.ManifestVersion {
		return result, refuse("apparatus-manifest-identity-mismatch", pathApparatusManifests, "selected apparatus manifest identity does not match its concrete payload")
	}
	digest, err := hash(json.RawMessage(raw))
	if err != nil {
		return result, err
	}
	if text(ref.Digest) != digest {
		return result, refuse("apparatus-manifest-digest-mismatch", pathApparatusManifests, "selected apparatus manifest digest does not match its concrete payload")
	}
	constructed := admission.ApparatusManifest{Backend: backend}
	if backend == nil {
		var processor binding.ProcessorManifestV2
		if decode(raw, &processor) != nil {
			return result, trialInvalid()
		}
		constructed.Processor = &processor
	}
	return apparatusReference{constructed, metadata, backend}, nil
}
func loadApparatusSelection(request Request, input compilationInputs, refs []reference) (apparatusSelection, error) {
	result := apparatusSelection{metadata: map[ApparatusManifestKey]manifestMetadata{}, backends: map[ApparatusManifestKey]binding.BackendManifestV2{}, capabilities: map[string]bool{}, manifests: map[ApparatusManifestKey]admission.ApparatusManifest{}}
	for _, ref := range refs {
		key, err := apparatusReferenceKey(ref)
		if err != nil {
			return result, err
		}
		if _, exists := result.metadata[key]; exists {
			return result, refuse("apparatus-manifest-duplicate", pathApparatusManifests, "selected apparatus contains duplicate concrete manifest identities")
		}
		admitted, err := resolveApparatusReference(request, input, key, ref, "selected apparatus manifest reference has no exact concrete payload")
		if err != nil {
			return result, err
		}
		result.metadata[key] = admitted.metadata
		result.manifests[key] = admitted.manifest
		if admitted.backend != nil {
			result.backends[key] = *admitted.backend
		}
		addManifestCapabilities(result.capabilities, key, admitted.metadata)
	}
	return result, nil
}
func selectedApparatus(request Request, input compilationInputs) (apparatusSelection, error) {
	var apparatus apparatusBinding
	if decode(input.apparatusJSON, &apparatus) != nil {
		return apparatusSelection{}, trialInvalid()
	}
	selected, err := loadApparatusSelection(request, input, apparatus.Manifests)
	if err != nil {
		return apparatusSelection{}, err
	}
	if err = admitApparatusEnvelope(request, apparatus, selected); err != nil {
		return apparatusSelection{}, err
	}
	declared, err := declaredApparatusCapabilities(apparatus.Capabilities, selected.capabilities)
	if err != nil {
		return apparatusSelection{}, err
	}
	if err = selectedCompatibility(selected.metadata, false); err != nil {
		return apparatusSelection{}, err
	}
	if err = validateApparatusIntent(input.spec.ApparatusIntent, selected.metadata, apparatus.Manifests, declared, false); err != nil {
		return apparatusSelection{}, err
	}
	return selected, nil
}
func admitApparatusEnvelope(request Request, apparatus apparatusBinding, selected apparatusSelection) error {
	if len(selected.backends) == 0 {
		return refuse("apparatus-envelope-unsupported", pathRealizationEnvelope, "selected backend manifests do not bind the admitted realization envelope")
	}
	identity, _, err := envelopeIdentity(request.RealizationEnvelope)
	if err != nil {
		return err
	}
	for key, manifest := range selected.metadata {
		if key.ComponentKind == componentBackend && !sameJSON(manifest.Envelope, identity) {
			return refuse("apparatus-envelope-unsupported", pathRealizationEnvelope, "selected backend manifests do not bind the admitted realization envelope")
		}
	}
	if !sameJSON(apparatus.Envelope, identity) {
		return refuse("realization-envelope-ref-mismatch", pathRealizationEnvelope, "apparatus realization-envelope identity does not match the supplied carrier")
	}
	return nil
}
func declaredApparatusCapabilities(claims []string, available map[string]bool) (map[string]bool, error) {
	declared := map[string]bool{}
	for _, claim := range claims {
		if !available[claim] {
			return nil, refuse("apparatus-capability-unproven", "/apparatus/capability_refs", "selected apparatus capability claims are not proven by concrete manifests")
		}
		declared[claim] = true
	}
	return declared, nil
}
