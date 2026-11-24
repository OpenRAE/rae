package admission

import (
	"encoding/json"
	"io"
	"math"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// associatedManifestLimits bound a serialized manifest. The byte bound is the
// reference loader's 16 MiB manifest ceiling.
func associatedManifestLimits() ingress.Limits {
	return ingress.Limits{MaxBytes: 16 * 1048576, MaxDepth: 64}
}

// AssociatedArtifactLimits are the caller's resource limits for one manifest
// validation. They apply before the published byte binding.
type AssociatedArtifactLimits struct{ MaxArtifacts, MaxTotalBytes, MaxArtifactBytes int }

// DefaultAssociatedArtifactLimits returns the reference defaults: 1,024
// artifacts, 4 GiB in total and 1 GiB for each artifact. A platform with a
// smaller int uses its largest int for the byte limits.
func DefaultAssociatedArtifactLimits() AssociatedArtifactLimits {
	return AssociatedArtifactLimits{MaxArtifacts: 1024, MaxTotalBytes: min(4<<30, math.MaxInt), MaxArtifactBytes: min(1<<30, math.MaxInt)}
}

// allows reports whether the limits are valid and the declared artifact sizes
// stay within them. The published binding still checks the actual bytes.
func (limits AssociatedArtifactLimits) allows(manifest any) bool {
	artifacts := object(at(manifest, "artifacts"))
	if limits.MaxArtifacts < 1 || limits.MaxTotalBytes < 0 || limits.MaxArtifactBytes < 0 || len(artifacts) > limits.MaxArtifacts {
		return false
	}
	var total int64
	for _, artifact := range artifacts {
		size, ok := integer(at(artifact, "size_bytes"))
		if !ok || size < 0 || int64(size) > int64(limits.MaxArtifactBytes) {
			return false
		}
		total += int64(size)
		if total > int64(limits.MaxTotalBytes) {
			return false
		}
	}
	return true
}

// LoadAssociatedManifest checks a manifest against its published schema and
// applies its defaults. The result makes no admission claim: use
// ValidateAssociatedManifest with the admitted parent and payload bytes.
func LoadAssociatedManifest(v *Validator, data []byte, limits ingress.Limits) (binding.AssociatedArtifactManifestV1, error) {
	var manifest binding.AssociatedArtifactManifestV1
	view, err := v.low.Defaulted(termAssociatedArtifactManifestV1, data, limits)
	if err != nil {
		return manifest, err
	}
	raw, err := json.Marshal(view)
	if err != nil {
		return manifest, invalid()
	}
	if err = json.Unmarshal(raw, &manifest); err != nil {
		return binding.AssociatedArtifactManifestV1{}, invalid()
	}
	return manifest, nil
}

// AssociatedArtifactSetDigest derives the published identity of the manifest's
// parent and artifact set. Authors compute it before payload admission.
func AssociatedArtifactSetDigest(manifest binding.AssociatedArtifactManifestV1) (string, error) {
	v, err := associatedDocument(manifest)
	if err != nil {
		return "", err
	}
	associatedSatisfactionDefaults(v)
	return associatedSetDigest(v)
}

// ValidateAssociatedManifest admits a manifest against its admitted parent and
// the caller's payload readers, one for each artifact ID. It never opens a
// locator. The readers replace any payloads that parent supplies.
func ValidateAssociatedManifest(v *Validator, manifest binding.AssociatedArtifactManifestV1, parent AssociatedArtifactsContext, readers map[string]io.Reader, limits AssociatedArtifactLimits) (validation.Value, error) {
	document, err := associatedDocument(manifest)
	if err != nil {
		return validation.Value{}, err
	}
	if !limits.allows(document) {
		return validation.Value{}, invalid()
	}
	if parent == nil {
		return validation.Value{}, contextRequired()
	}
	data, err := json.Marshal(manifest)
	if err != nil {
		return validation.Value{}, invalid()
	}
	return v.Validate(termAssociatedArtifactManifestV1, data, associatedManifestLimits(), associatedPayloads{parent, readers})
}

// associatedDocument returns the closed JSON form of a transport manifest.
func associatedDocument(manifest binding.AssociatedArtifactManifestV1) (any, error) {
	data, err := json.Marshal(manifest)
	if err != nil {
		return nil, invalid()
	}
	return ingress.Parse(data, associatedManifestLimits(), ingress.Object)
}

// associatedPayloads binds the parent identity to the caller's readers.
type associatedPayloads struct {
	AssociatedArtifactsContext

	readers map[string]io.Reader
}

func (c associatedPayloads) AssociatedPayloads() map[string]io.Reader { return c.readers }
