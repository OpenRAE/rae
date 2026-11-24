package module

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"io/fs"
	"path"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	sdlsource "github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func lockFieldNames() [10]string {
	return [...]string{"source", "namespace", termRequestedVersion, "resolved_source", termModuleID, termModuleVersion, "manifest_digest", termContentDigest, "export_hash", termSignerID}
}
func lockField(record *LockRecord, key string) *string {
	switch key {
	case "source":
		return &record.Source
	case "namespace":
		return &record.Namespace
	case termRequestedVersion:
		return &record.RequestedVersion
	case "resolved_source":
		return &record.ResolvedSource
	case termModuleID:
		return &record.ModuleID
	case termModuleVersion:
		return &record.ModuleVersion
	case "manifest_digest":
		return &record.ManifestDigest
	case termContentDigest:
		return &record.ContentDigest
	case "export_hash":
		return &record.ExportHash
	case termSignerID:
		return &record.SignerID
	}
	return nil
}

// DecodeLockfile uses the strict, bounded JSON owner, including duplicate keys.
func DecodeLockfile(raw []byte) (Lockfile, error) {
	result := Lockfile{SchemaVersion: termRaesLockV1, Imports: []LockRecord{}}
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(sdlsource.DefaultLimits().MaxInputBytes), MaxDepth: 8}, ingress.Object)
	if err != nil {
		return result, invalid()
	}
	root := object(value)
	if !closedPolicy(root, []string{termSchemaVersion, "imports"}) {
		return result, invalid()
	}
	if version, exists := root[termSchemaVersion]; exists && version != result.SchemaVersion {
		return result, invalid()
	}
	rows, ok := root["imports"].([]any)
	if _, exists := root["imports"]; exists && !ok {
		return result, invalid()
	}
	for _, value := range rows {
		record, err := decodeLockRecord(object(value))
		if err != nil {
			return result, err
		}
		result.Imports = append(result.Imports, record)
	}
	return result, nil
}
func decodeLockRecord(row map[string]any) (LockRecord, error) {
	record := LockRecord{RequestedVersion: "*"}
	if row == nil {
		return record, invalid()
	}
	for key, value := range row {
		field := lockField(&record, key)
		text, ok := value.(string)
		if field == nil || !ok {
			return record, invalid()
		}
		*field = text
	}
	for _, key := range lockFieldNames() {
		if key == termRequestedVersion || key == termSignerID {
			continue
		}
		if _, present := row[key]; !present {
			return record, invalid()
		}
	}
	return record, nil
}

// LoadLockfile reads only the explicit filesystem and returns an empty lock if absent.
func LoadLockfile(source fs.FS, directory string) (Lockfile, error) {
	raw, err := readSourceFile(source, path.Join(directory, LockfileName))
	if errors.Is(err, fs.ErrNotExist) {
		return Lockfile{SchemaVersion: termRaesLockV1, Imports: []LockRecord{}}, nil
	}
	if err != nil {
		return Lockfile{}, operational(err)
	}
	return DecodeLockfile(raw)
}

// ResolveLock resolves the root's direct imports. A post-verification callback
// grants no network authority; that authority requires an explicit Registry.
func ResolveLock(ctx context.Context, source fs.FS, root string, trust TrustPolicy, admitters ...SourceAdmitter) (Lockfile, error) {
	if registry, ok := trust.(*Registry); ok {
		return registry.ResolveLock(ctx, source, root, admitters...)
	}
	if trust == nil {
		policy := DefaultPolicy()
		raw, err := readSourceFile(source, path.Join(path.Dir(root), "raes-trust.yaml"))
		if err == nil {
			policy, err = DecodePolicy(raw)
		}
		if err != nil && !errors.Is(err, fs.ErrNotExist) {
			return Lockfile{}, err
		}
		trust = policy
	}
	models, err := moduleModels()
	if err != nil {
		return Lockfile{}, err
	}
	return resolveRecords(ctx, source, root, &Registry{models: models, limits: defaultResourceLimits(), trust: trust}, admitters)
}

// ResolveLock uses this registry's explicit policy, transport and cache.
func (r *Registry) ResolveLock(ctx context.Context, source fs.FS, root string, admitters ...SourceAdmitter) (Lockfile, error) {
	if r == nil {
		return Lockfile{}, invalid()
	}
	return resolveRecords(ctx, source, root, r, admitters)
}

// SourceAdmitter checks one complete imported authoring source. It performs
// no import expansion and must not change the bytes used for lock identities.
type SourceAdmitter interface{ AdmitModuleSource(raw []byte) error }

func resolveRecords(ctx context.Context, files fs.FS, root string, r *Registry, admitters []SourceAdmitter) (Lockfile, error) {
	result := Lockfile{SchemaVersion: termRaesLockV1, Imports: []LockRecord{}}
	if len(admitters) > 1 || len(admitters) == 1 && admitters[0] == nil {
		return result, invalid()
	}
	var admitter SourceAdmitter
	if len(admitters) == 1 {
		admitter = admitters[0]
	}
	raw, err := readSourceFile(files, root)
	if err != nil {
		return result, operational(err)
	}
	payload, err := r.lockRootPayload(raw)
	if err != nil {
		return result, err
	}
	rows, _ := payload["imports"].([]any)
	for _, row := range rows {
		if err = ctx.Err(); err != nil {
			return result, operational(err)
		}
		record, resolveErr := r.resolveImportRecord(ctx, files, root, object(row), admitter)
		if resolveErr != nil {
			return result, resolveErr
		}
		result.Imports = append(result.Imports, record)
	}
	return result, nil
}
func (r *Registry) resolveImportRecord(ctx context.Context, files fs.FS, root string, decl map[string]any, admitter SourceAdmitter) (LockRecord, error) {
	reference := importReference(decl)
	version := text(decl["version"])
	if version == "" {
		version = "*"
	}
	var record LockRecord
	var err error
	switch {
	case strings.HasPrefix(reference, "oci:"):
		bundle, resolveErr := r.Resolve(ctx, reference, version, text(decl["digest"]))
		if resolveErr != nil {
			return LockRecord{}, resolveErr
		}
		if !allowedParameters(decl, bundle.parameters) {
			return LockRecord{}, invalid()
		}
		record = bundle.Record()
	case strings.HasPrefix(reference, termLocalPrefix):
		record, err = r.localRecord(ctx, files, root, decl, reference, version, admitter)
		if err != nil {
			return LockRecord{}, err
		}
	default:
		return LockRecord{}, invalid()
	}
	record.Source = reference
	record.Namespace = text(decl["namespace"])
	record.RequestedVersion = version
	return record, nil
}
func (r *Registry) lockRootPayload(raw []byte) (map[string]any, error) {
	options := sdlsource.DefaultOptions()
	options.RequireMapping = true
	document, err := sdlsource.Decode(raw, options)
	if err != nil {
		return nil, err
	}
	payload := object(document.NormalizedValue())
	if value, present := payload["imports"]; present {
		if _, ok := value.([]any); !ok {
			return nil, invalid()
		}
	}
	rows, _ := payload["imports"].([]any)
	for _, value := range rows {
		encoded, err := json.Marshal(value)
		if err != nil {
			return nil, err
		}
		if err = r.models.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/ImportDecl", encoded, ingress.Limits{MaxBytes: int(options.Limits.MaxInputBytes)}); err != nil {
			return nil, err
		}
	}
	return payload, nil
}
func (r *Registry) localRecord(ctx context.Context, files fs.FS, root string, decl map[string]any, reference, version string, admitter SourceAdmitter) (LockRecord, error) {
	relative := strings.TrimPrefix(reference, termLocalPrefix)
	name, err := sdlsource.ResolvePath(path.Dir(root), relative)
	if err != nil {
		return LockRecord{}, err
	}
	raw, err := readSourceFile(files, name)
	if err != nil {
		return LockRecord{}, operational(err)
	}
	payload, err := r.sourcePayload(raw, admitter)
	if err != nil {
		return LockRecord{}, err
	}
	encoded, err := json.Marshal(payload["module"])
	if err != nil {
		return LockRecord{}, invalid()
	}
	descriptor, err := r.descriptor(encoded)
	if err != nil {
		return LockRecord{}, err
	}
	requirement, err := versionSpec(version)
	if err != nil || !requirement.accepts(descriptor.Version) {
		return LockRecord{}, invalid()
	}
	content := digest.SHA256(raw)
	if pin := text(decl["digest"]); pin != "" && pin != content {
		return LockRecord{}, invalid()
	}
	if !allowedParameters(decl, descriptor.Parameters) {
		return LockRecord{}, invalid()
	}
	exports, err := sortedBytes(descriptor.Exports, false)
	if err != nil {
		return LockRecord{}, err
	}
	record := LockRecord{ModuleID: descriptor.ID, ModuleVersion: descriptor.Version, ResolvedSource: strings.ReplaceAll(relative, "\\", "/"), ContentDigest: content, ExportHash: strings.TrimPrefix(digest.SHA256(exports), termSHA256Prefix)}
	record.Source, record.Namespace, record.RequestedVersion = reference, text(decl["namespace"]), version
	facts := VerificationFacts{Record: record, LocalSource: true, ContentVerified: true, ExportsVerified: true}
	if r.cache != nil {
		err = r.AdmitModule(ctx, facts)
	} else if r.trust != nil {
		err = r.trust.AdmitModule(ctx, facts)
	}
	return record, err
}
func allowedParameters(decl map[string]any, parameters []string) bool {
	known := map[string]bool{}
	for _, name := range parameters {
		known[name] = true
	}
	for name := range object(decl["parameters"]) {
		if !known[name] {
			return false
		}
	}
	return true
}
func importReference(decl map[string]any) string {
	if reference := text(decl["source"]); reference != "" {
		return reference
	}
	return termLocalPrefix + text(decl["path"])
}
func (r *Registry) sourcePayload(raw []byte, admitter SourceAdmitter) (map[string]any, error) {
	options := sdlsource.DefaultOptions()
	options.RequireMapping = true
	document, err := sdlsource.Decode(raw, options)
	if err != nil {
		return nil, err
	}
	payload := object(document.NormalizedValue())
	if admitter != nil {
		return payload, admitter.AdmitModuleSource(append([]byte(nil), raw...))
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, invalid()
	}
	if err = r.models.CheckSDLConstruction("sdl-authoring-input-v1", "#", encoded, ingress.Limits{MaxBytes: int(options.Limits.MaxInputBytes)}); err != nil {
		return nil, err
	}
	return payload, nil
}
func readSourceFile(files fs.FS, name string) ([]byte, error) {
	if files == nil || !fs.ValidPath(name) {
		return nil, invalid()
	}
	file, err := files.Open(name)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() {
		return nil, invalid()
	}
	limit := sdlsource.DefaultLimits().MaxInputBytes
	if info.Size() > limit {
		return nil, invalid()
	}
	raw, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil || int64(len(raw)) > limit {
		return nil, invalid()
	}
	return raw, nil
}

// ResolveLocked verifies the exact locked manifest without selecting a new tag.
func (r *Registry) ResolveLocked(ctx context.Context, record LockRecord) (*Bundle, error) {
	return r.resolve(ctx, record.Source, record.RequestedVersion, record.ContentDigest, &record)
}
