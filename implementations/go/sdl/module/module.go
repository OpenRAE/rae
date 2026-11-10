// Package module owns explicit module trust, verified source bundles, OCI
// persistence and local publication. A bundle grants no SDL semantic admission.
package module

import (
	"context"
	"io/fs"
	"maps"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
	"unicode"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// LockfileName is the workspace lock filename.
const LockfileName = "raes.lock.json"

// Lockfile records resolved source identities in import order.
type Lockfile struct {
	SchemaVersion string
	Imports       []LockRecord
}

// LockRecord separates requested, manifest, content and export identities.
type LockRecord struct {
	Source, Namespace, RequestedVersion, ResolvedSource                          string
	ModuleID, ModuleVersion, ManifestDigest, ContentDigest, ExportHash, SignerID string
}

// VerificationFacts are a resolver observation, not authority to create a bundle.
type VerificationFacts struct {
	Record                                                                             LockRecord
	Registry, SignerPublicKey                                                          string
	LocalSource, SignatureVerified, ManifestVerified, ContentVerified, ExportsVerified bool
}

// TrustPolicy can narrow admission after native integrity verification.
type TrustPolicy interface {
	AdmitModule(ctx context.Context, facts VerificationFacts) error
}

// RegistryTrust supplies the explicit pre-fetch policy for one registry.
type RegistryTrust struct {
	RequireSignatures, AllowInsecureHTTP bool
	TrustedSigners                       map[string]string
}

// Policy is the typed workspace trust configuration.
type Policy struct {
	SchemaVersion             string
	AllowUnsignedLocalSources bool
	Registries                map[string]RegistryTrust
}

// DefaultPolicy allows local sources and grants no registry authority.
func DefaultPolicy() Policy {
	return Policy{SchemaVersion: "raes-trust/v1", AllowUnsignedLocalSources: true, Registries: map[string]RegistryTrust{}}
}

// AdmitModule evaluates resolver facts without creating verified source authority.
func (policy Policy) AdmitModule(ctx context.Context, facts VerificationFacts) error {
	if err := ctx.Err(); err != nil {
		return operational(err)
	}
	if facts.LocalSource {
		if !policy.AllowUnsignedLocalSources || !facts.ContentVerified || !facts.ExportsVerified {
			return invalid()
		}
		return nil
	}
	rule, allowed := policy.Registries[facts.Registry]
	if !allowed || !facts.ManifestVerified || !facts.ContentVerified || !facts.ExportsVerified {
		return invalid()
	}
	if rule.RequireSignatures {
		key, known := rule.TrustedSigners[facts.Record.SignerID]
		if !facts.SignatureVerified || !known || key != facts.SignerPublicKey {
			return invalid()
		}
	}
	return nil
}

// Artifact contains exact received OCI bytes, before verification.
type Artifact struct{ Manifest, Config, Bundle []byte }

// Publication identifies the usable immutable local OCI layout.
type Publication struct {
	LayoutDir      string `json:"layout_dir"`
	ModuleID       string `json:"module_id"`
	ModuleVersion  string `json:"module_version"`
	ManifestDigest string `json:"manifest_digest"`
	ContentDigest  string `json:"content_digest"`
	ExportHash     string `json:"export_hash"`
	SignerID       string `json:"signer_id"`
}

// Registry binds transport and persistence to explicitly supplied authority.
type Registry struct {
	policy    Policy
	trust     TrustPolicy
	cache     *os.Root
	directory string
	limits    resourceLimits
	models    *admission.Validator
}

// Bundle owns copied sources and integrity facts from successful verification.
type Bundle struct {
	root, path string
	sources    map[string][]byte
	record     LockRecord
	parameters []string
}

// RootFile returns the signed relative entrypoint.
func (b *Bundle) RootFile() string { return b.root }

// RootPath returns the immutable cache entrypoint's diagnostic identity.
func (b *Bundle) RootPath() string { return b.path }

// Sources returns independent copies of the verified, reachable source graph.
func (b *Bundle) Sources() map[string][]byte {
	result := make(map[string][]byte, len(b.sources))
	for name, raw := range b.sources {
		result[name] = slices.Clone(raw)
	}
	return result
}

// Record returns the distinct verified identity facts.
func (b *Bundle) Record() LockRecord { return b.record }

// Only packaged immutable schemas and predicates are process-wide. No caller
// policy, request, filesystem or trust callback enters this shared value.
var moduleModels = sync.OnceValues(admission.New) //nolint:gochecknoglobals // The stock validator is immutable and safe to share.

// NewRegistry opens only the explicitly supplied cache and copies pre-fetch policy.
func NewRegistry(cacheDirectory string, policy Policy, trust TrustPolicy) (*Registry, error) {
	if cacheDirectory == "" {
		return nil, invalid()
	}
	if err := os.MkdirAll(cacheDirectory, 0o700); err != nil {
		return nil, operational(err)
	}
	before, err := os.Lstat(cacheDirectory)
	if err != nil {
		return nil, operational(err)
	}
	if !before.IsDir() || before.Mode()&os.ModeSymlink != 0 {
		return nil, invalid()
	}
	cache, err := os.OpenRoot(cacheDirectory)
	if err != nil {
		return nil, operational(err)
	}
	after, err := fs.Stat(cache.FS(), ".")
	if err != nil || !os.SameFile(before, after) {
		_ = cache.Close()
		return nil, invalid()
	}
	models, err := moduleModels()
	if err != nil {
		_ = cache.Close()
		return nil, err
	}
	directory, err := filepath.Abs(cacheDirectory)
	if err != nil {
		_ = cache.Close()
		return nil, operational(err)
	}
	policyCopy := policy
	policyCopy.Registries = maps.Clone(policy.Registries)
	for name, rule := range policyCopy.Registries {
		rule.TrustedSigners = maps.Clone(rule.TrustedSigners)
		policyCopy.Registries[name] = rule
	}
	return &Registry{policy: policyCopy, trust: trust, cache: cache, directory: directory, limits: defaultResourceLimits(), models: models}, nil
}

// Close releases the registry's rooted cache descriptor.
func (r *Registry) Close() error {
	if r == nil || r.cache == nil {
		return nil
	}
	return r.cache.Close()
}

// AdmitModule applies pre-fetch policy followed by the optional narrowing callback.
func (r *Registry) AdmitModule(ctx context.Context, facts VerificationFacts) error {
	if r == nil {
		return invalid()
	}
	if err := r.policy.AdmitModule(ctx, facts); err != nil {
		return err
	}
	if r.trust != nil {
		if err := r.trust.AdmitModule(ctx, facts); err != nil {
			return fault.New(fault.Authorization, "sdl-module-trust-refused", err)
		}
	}
	return nil
}

type resourceLimits struct {
	metadataBytes, bundleBytes, memberBytes, totalBytes, tarBytes, expansionRatio int64
	members, depth                                                                int
}

func defaultResourceLimits() resourceLimits {
	return resourceLimits{metadataBytes: 8 << 20, bundleBytes: 128 << 20, memberBytes: 64 << 20, totalBytes: 256 << 20, tarBytes: 320 << 20, expansionRatio: 1024, members: 8192, depth: 256}
}

func invalid() error { return fault.New(fault.InvalidInput, "sdl-module-invalid", nil) }
func operational(cause error) error {
	return fault.New(fault.Operational, "sdl-module-operation", cause)
}
func object(value any) map[string]any { result, _ := value.(map[string]any); return result }
func text(value any) string           { result, _ := value.(string); return result }
func lower(value string) string       { return strings.ToLower(value) }
func pythonTrim(value string) string {
	return strings.TrimFunc(value, func(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f })
}

const (
	mappingSyntax     = "mapping"
	sequenceSyntax    = "sequence"
	scalarSyntax      = "scalar"
	nullType          = "null"
	arbitraryEquality = "==="
)
