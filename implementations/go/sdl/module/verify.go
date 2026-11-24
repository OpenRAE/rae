package module

import (
	"context"
	"crypto/ed25519"
	"encoding/json"
	"maps"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const (
	manifestMediaType = "application/vnd.oci.image.manifest.v1+json"
	configMediaType   = "application/vnd.raes.module.config.v1+json"
	bundleMediaType   = "application/vnd.raes.module.bundle.v1+tar+gzip"
	cacheManifestName = ".raes-cache-tree.json"
)

type blobDescriptor struct {
	MediaType string `json:"mediaType"`
	Digest    string `json:"digest"`
	Size      int64  `json:"size"`
}
type ociManifest struct {
	SchemaVersion int               `json:"schemaVersion"`
	MediaType     string            `json:"mediaType"`
	Config        blobDescriptor    `json:"config"`
	Layers        []blobDescriptor  `json:"layers"`
	Annotations   map[string]string `json:"annotations,omitempty"`
}
type moduleDescriptor struct {
	ID          string              `json:"id"`
	Version     string              `json:"version"`
	Parameters  []string            `json:"parameters"`
	Exports     map[string][]string `json:"exports"`
	Description string              `json:"description"`
}
type moduleConfig struct {
	SchemaVersion string          `json:"schema_version"`
	Root          json.RawMessage `json:"root_file"`
	Module        json.RawMessage `json:"module"`
	Signatures    json.RawMessage `json:"signatures"`
}
type signatureRecord struct {
	Signer    string `json:"signer_id"`
	Signature string `json:"signature"`
}

// Verify independently checks exact OCI bytes and captures verified sources.
func (r *Registry) Verify(ctx context.Context, registry string, artifact Artifact) (*Bundle, error) {
	return r.verify(ctx, registry, artifact, LockRecord{}, nil)
}
func (r *Registry) verify(ctx context.Context, registry string, artifact Artifact, requested LockRecord, constraints *resolutionConstraints) (*Bundle, error) {
	if r == nil || r.models == nil || r.cache == nil {
		return nil, invalid()
	}
	rule, allowed := r.policy.Registries[registry]
	if !allowed {
		return nil, invalid()
	}
	if err := ctx.Err(); err != nil {
		return nil, operational(err)
	}
	layer, err := r.artifactLayer(artifact)
	if err != nil {
		return nil, err
	}
	config, err := r.decodeModuleConfig(artifact.Config)
	if err != nil {
		return nil, err
	}
	root, descriptor := config.root, config.descriptor
	signer, publicKey, err := verifySignatures(descriptor, layer.Digest, root, config.signatures, rule)
	if err != nil {
		return nil, err
	}
	inventory, err := inspectArchive(artifact.Bundle, layer.Digest, root, r.limits)
	if err != nil {
		return nil, err
	}
	if err = r.checkSourceDescriptor(inventory, root, descriptor); err != nil {
		return nil, err
	}
	exports, err := sortedBytes(descriptor.Exports, false)
	if err != nil {
		return nil, err
	}
	record := LockRecord{ModuleID: descriptor.ID, ModuleVersion: descriptor.Version, ManifestDigest: digest.SHA256(artifact.Manifest), ContentDigest: layer.Digest, ExportHash: strings.TrimPrefix(digest.SHA256(exports), "sha256:"), SignerID: signer}
	if constraints != nil && !resolvedModuleMatches(record, constraints.version, constraints.pin, constraints.locked) {
		return nil, invalid()
	}
	record.Source, record.RequestedVersion, record.ResolvedSource = requested.Source, requested.RequestedVersion, requested.ResolvedSource
	facts := VerificationFacts{Record: record, Registry: registry, SignerPublicKey: publicKey, SignatureVerified: signer != "", ManifestVerified: true, ContentVerified: true, ExportsVerified: true}
	if err = r.AdmitModule(ctx, facts); err != nil {
		return nil, err
	}
	sources, err := captureSources(inventory.files, root)
	if err != nil {
		return nil, err
	}
	rootPath, err := r.publishCache(ctx, inventory, record.ManifestDigest, root)
	if err != nil {
		return nil, err
	}
	return &Bundle{root: root, path: rootPath, sources: sources, record: record, parameters: descriptor.Parameters}, nil
}
func (r *Registry) checkSourceDescriptor(inventory archiveInventory, root string, descriptor moduleDescriptor) error {
	rootData, exists := inventory.files[root]
	if !exists {
		return invalid()
	}
	actual, err := r.sourceDescriptor(rootData)
	if err != nil || !sameDescriptor(actual, descriptor) {
		return invalid()
	}
	return nil
}
func (r *Registry) artifactLayer(artifact Artifact) (blobDescriptor, error) {
	manifest, layer, err := r.readManifest(artifact.Manifest)
	if err != nil {
		return blobDescriptor{}, err
	}
	if int64(len(artifact.Config)) > r.limits.metadataBytes || digest.SHA256(artifact.Config) != manifest.Config.Digest {
		return blobDescriptor{}, invalid()
	}
	if int64(len(artifact.Bundle)) > r.limits.bundleBytes || digest.SHA256(artifact.Bundle) != layer.Digest {
		return blobDescriptor{}, invalid()
	}
	return layer, nil
}

type decodedModuleConfig struct {
	root       string
	descriptor moduleDescriptor
	signatures json.RawMessage
}

func (r *Registry) decodeModuleConfig(raw []byte) (decodedModuleConfig, error) {
	var config moduleConfig
	if !utf8.Valid(raw) || json.Unmarshal(raw, &config) != nil {
		return decodedModuleConfig{}, invalid()
	}
	descriptor, err := r.descriptor(config.Module)
	if err != nil {
		return decodedModuleConfig{}, err
	}
	root := "module.yaml"
	if len(config.Root) != 0 {
		var declared *string
		if json.Unmarshal(config.Root, &declared) != nil || declared == nil {
			return decodedModuleConfig{}, invalid()
		}
		root = *declared
	}
	if !validArchivePath(root, false, r.limits.depth) {
		return decodedModuleConfig{}, invalid()
	}
	return decodedModuleConfig{root, descriptor, config.Signatures}, nil
}
func (r *Registry) readManifest(raw []byte) (ociManifest, blobDescriptor, error) {
	var manifest ociManifest
	if len(raw) == 0 || int64(len(raw)) > r.limits.metadataBytes || !utf8.Valid(raw) || json.Unmarshal(raw, &manifest) != nil {
		return manifest, blobDescriptor{}, invalid()
	}
	if !digest.Valid(manifest.Config.Digest) {
		return manifest, blobDescriptor{}, invalid()
	}
	for _, layer := range manifest.Layers {
		if layer.MediaType == bundleMediaType && digest.Valid(layer.Digest) {
			return manifest, layer, nil
		}
	}
	return manifest, blobDescriptor{}, invalid()
}
func (r *Registry) descriptor(raw []byte) (moduleDescriptor, error) {
	var descriptor moduleDescriptor
	if r.models.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/ModuleDescriptor", raw, ingress.Limits{MaxBytes: int(r.limits.metadataBytes)}) != nil {
		return descriptor, invalid()
	}
	if json.Unmarshal(raw, &descriptor) != nil {
		return descriptor, invalid()
	}
	if descriptor.Exports == nil {
		descriptor.Exports = map[string][]string{}
	}
	if descriptor.Parameters == nil {
		descriptor.Parameters = []string{}
	}
	if !uniqueNames(descriptor.Parameters) {
		return descriptor, invalid()
	}
	for _, names := range descriptor.Exports {
		if !uniqueNames(names) {
			return descriptor, invalid()
		}
	}
	return descriptor, nil
}
func uniqueNames(names []string) bool {
	seen := map[string]bool{}
	for _, name := range names {
		if seen[name] {
			return false
		}
		seen[name] = true
	}
	return true
}
func (r *Registry) sourceDescriptor(raw []byte) (moduleDescriptor, error) {
	options := source.DefaultOptions()
	options.RequireMapping = true
	parsed, err := source.Decode(raw, options)
	if err != nil {
		return moduleDescriptor{}, err
	}
	value := object(parsed.NormalizedValue())
	encoded, err := json.Marshal(value["module"])
	if err != nil {
		return moduleDescriptor{}, err
	}
	return r.descriptor(encoded)
}
func sameDescriptor(first, second moduleDescriptor) bool {
	return first.ID == second.ID && first.Version == second.Version && maps.EqualFunc(first.Exports, second.Exports, func(a, b []string) bool { return strings.Join(a, "\x00") == strings.Join(b, "\x00") })
}

func sortedBytes(value any, newline bool) ([]byte, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return nil, err
	}
	canonical, err := canonjson.Sorted(raw, true)
	if err != nil {
		return nil, err
	}
	if newline {
		canonical = append(canonical, '\n')
	}
	return canonical, nil
}
func signablePayload(descriptor moduleDescriptor, contentDigest, root string) ([]byte, error) {
	return sortedBytes(map[string]any{termModuleID: descriptor.ID, termModuleVersion: descriptor.Version, "exports": descriptor.Exports, termContentDigest: contentDigest, termRootFile: root}, false)
}
func verifySignatures(descriptor moduleDescriptor, contentDigest, root string, raw json.RawMessage, policy RegistryTrust) (string, string, error) {
	if !policy.RequireSignatures {
		return "", "", nil
	}
	signatures, err := decodeSignatureCandidates(raw)
	if err != nil {
		return "", "", err
	}
	payload, err := signablePayload(descriptor, contentDigest, root)
	if err != nil {
		return "", "", err
	}
	for _, record := range signatures {
		signature, valid := decodeSignatureCandidate(record)
		if !valid {
			continue
		}
		encoded, known := policy.TrustedSigners[signature.Signer]
		if !known || signature.Signer == "" || signature.Signature == "" {
			continue
		}
		key, err := decodeSignatureBase64(encoded)
		if err != nil || len(key) != ed25519.PublicKeySize {
			continue
		}
		value, err := decodeSignatureBase64(signature.Signature)
		if err == nil && ed25519.Verify(ed25519.PublicKey(key), payload, value) {
			return signature.Signer, encoded, nil
		}
	}
	return "", "", invalid()
}

func decodeSignatureCandidates(raw json.RawMessage) ([]map[string]json.RawMessage, error) {
	var signatures []map[string]json.RawMessage
	if len(raw) != 0 && json.Unmarshal(raw, &signatures) != nil {
		return nil, invalid()
	}
	for _, record := range signatures {
		if record == nil {
			return nil, invalid()
		}
	}
	return signatures, nil
}

func decodeSignatureCandidate(record map[string]json.RawMessage) (signatureRecord, bool) {
	var signature signatureRecord
	valid := json.Unmarshal(record["signer_id"], &signature.Signer) == nil && json.Unmarshal(record["signature"], &signature.Signature) == nil
	return signature, valid
}
