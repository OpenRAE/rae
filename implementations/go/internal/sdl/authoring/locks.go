package authoring

import (
	"errors"
	"io/fs"
	"path"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type lockfile struct{ records []map[string]any }

func strictPin(pin string) bool {
	return len(pin) == 71 && strings.HasPrefix(pin, sha256Prefix) && strings.IndexFunc(pin[7:], func(r rune) bool { return (r < '0' || r > '9') && (r < 'a' || r > 'f') }) < 0
}
func pinMatches(raw []byte, pin string) bool {
	return pin == "" || strings.TrimPrefix(pin, sha256Prefix) == strings.TrimPrefix(digest.SHA256(raw), sha256Prefix)
}
func (c *composition) optional(name string) ([]byte, bool, error) {
	if c.supplied != nil {
		raw, err := c.supplied.Bytes(name)
		if code, ok := errors.AsType[interface {
			error
			Code() string
		}](err); ok && code.Code() == "sdl.import.source-missing" {
			return nil, false, nil
		}
		return raw, err == nil, err
	}
	if c.request.FS == nil {
		return nil, false, nil
	}
	resolved, err := c.fileName(name)
	if err != nil {
		return nil, false, workspaceFailure(name, err)
	}
	_, err = fs.Stat(c.request.FS, resolved)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, workspaceFailure(name, err)
	}
	raw, err := c.readBounded(resolved, source.DefaultLimits().MaxInputBytes)
	if err != nil {
		return nil, false, workspaceFailure(name, err)
	}
	return raw, err == nil, err
}

//nolint:nilnil // A missing optional lock is distinct from an empty lock.
func (c *composition) lock(importer string, needed bool) (*lockfile, error) {
	if !needed && c.supplied != nil {
		return nil, nil
	}
	raw, present, err := c.optional(path.Join(path.Dir(importer), "raes.lock.json"))
	if err != nil || !present {
		return nil, err
	}
	limit := source.DefaultLimits().MaxInputBytes
	if c.supplied != nil {
		limit = c.parser.limits.MaxInputBytes
		if err = c.budget.AddBytes(int64(len(raw))); err != nil {
			return nil, err
		}
	}
	return decodeLock(raw, limit)
}
func decodeLock(raw []byte, limit int64) (*lockfile, error) {
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(limit), MaxDepth: 8}, ingress.Object)
	if err != nil {
		return nil, importError(lockInvalidCode)
	}
	value := object(decoded)
	if !closed(value, nil, []string{"schema_version", importsField}) {
		return nil, importError(lockInvalidCode)
	}
	if version, ok := value["schema_version"]; ok && version != "raes-lock/v1" {
		return nil, importError(lockInvalidCode)
	}
	rows, ok := value[importsField].([]any)
	if _, present := value[importsField]; present && !ok {
		return nil, importError(lockInvalidCode)
	}
	lock := &lockfile{}
	for _, raw := range rows {
		record, err := decodeLockRecord(object(raw))
		if err != nil {
			return nil, err
		}
		lock.records = append(lock.records, record)
	}
	return lock, nil
}
func decodeLockRecord(record map[string]any) (map[string]any, error) {
	if !closed(record, []string{sourceField, namespaceField, resolvedSourceField, moduleIDField, moduleVersionField, manifestDigestField, contentDigestField, exportHashField}, []string{requestedVersionField, signerIDField}) {
		return nil, importError(lockInvalidCode)
	}
	for _, value := range record {
		if _, ok := value.(string); !ok {
			return nil, importError(lockInvalidCode)
		}
	}
	if _, present := record[requestedVersionField]; !present {
		record[requestedVersionField] = "*"
	}
	if _, present := record[signerIDField]; !present {
		record[signerIDField] = ""
	}
	return record, nil
}
func closed(value map[string]any, required, optional []string) bool {
	if value == nil {
		return false
	}
	for _, key := range required {
		if _, ok := value[key]; !ok {
			return false
		}
	}
	for key := range value {
		if !slices.Contains(required, key) && !slices.Contains(optional, key) {
			return false
		}
	}
	return true
}
func (c *composition) checkLock(lock *lockfile, decl, descriptor map[string]any, raw []byte, requested, relative string) error {
	record, present, err := matchingLockRecord(lock, decl, requested, c.supplied != nil)
	if err != nil || !present {
		return err
	}
	if c.supplied == nil {
		if !pinMatches(raw, text(record[contentDigestField])) {
			return importError("digest-mismatch")
		}
		return nil
	}
	exports, err := exportDigest(descriptor)
	if err != nil {
		return err
	}
	expected := map[string]any{resolvedSourceField: relative, moduleIDField: descriptor["id"], moduleVersionField: descriptor["version"], contentDigestField: digest.SHA256(raw), exportHashField: strings.TrimPrefix(exports, sha256Prefix), manifestDigestField: "", signerIDField: ""}
	for key, want := range expected {
		if record[key] != want {
			return importError("lock-mismatch")
		}
	}
	return nil
}
func matchingLockRecord(lock *lockfile, decl map[string]any, requested string, required bool) (map[string]any, bool, error) {
	if lock == nil {
		if required {
			return nil, false, importError("lock-missing")
		}
		return nil, false, nil
	}
	version := text(decl["version"])
	if version == "" {
		version = "*"
	}
	matches := []map[string]any{}
	for _, record := range lock.records {
		if record[sourceField] == requested && record[namespaceField] == decl[namespaceField] && record[requestedVersionField] == version {
			matches = append(matches, record)
		}
	}
	if len(matches) == 0 {
		if required {
			return nil, false, importError("lock-record-missing")
		}
		return nil, false, nil
	}
	if required && len(matches) != 1 {
		return nil, false, importError("lock-ambiguous")
	}
	return matches[0], true, nil
}
func (c *composition) trust(importer string) error {
	name := path.Join(path.Dir(importer), "raes-trust.yaml")
	raw, present, err := c.optional(name)
	if err != nil || !present {
		return err
	}
	if emptyPolicy(raw) {
		return nil
	}
	value, err := workspacePolicy(raw, name)
	if err != nil {
		return workspaceFailure(name, err)
	}
	if !validTrustPolicy(value) {
		return workspaceFailure(name, invalid())
	}
	if allowed, ok := value["allow_unsigned_local_sources"]; ok {
		normalized, err := normalizeBoolean(allowed, false)
		if err != nil {
			return workspaceFailure(name, err)
		}
		c.localDenied[importer] = normalized == false
	}
	return nil
}

func emptyPolicy(raw []byte) bool {
	for line := range strings.SplitSeq(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line != "" && !strings.HasPrefix(line, "#") {
			return false
		}
	}
	return true
}
func validTrustPolicy(value map[string]any) bool {
	if !closed(value, nil, []string{"schema_version", "allow_unsigned_local_sources", "registries"}) {
		return false
	}
	if version, present := value["schema_version"]; present {
		if _, ok := version.(string); !ok {
			return false
		}
	}
	raw, present := value["registries"]
	if !present {
		return true
	}
	registries := object(raw)
	if registries == nil {
		return false
	}
	for _, raw := range registries {
		if !validRegistryTrust(object(raw)) {
			return false
		}
	}
	return true
}
func validRegistryTrust(value map[string]any) bool {
	if !closed(value, nil, []string{"require_signatures", "trusted_signers", "allow_insecure_http"}) {
		return false
	}
	for _, key := range []string{"require_signatures", "allow_insecure_http"} {
		if raw, present := value[key]; present {
			if _, err := normalizeBoolean(raw, false); err != nil {
				return false
			}
		}
	}
	raw, present := value["trusted_signers"]
	if !present {
		return true
	}
	signers := object(raw)
	if signers == nil {
		return false
	}
	for _, raw := range signers {
		if _, ok := raw.(string); !ok {
			return false
		}
	}
	return true
}
func (c *composition) resolveLocked(decl map[string]any, lock *lockfile) (map[string]any, error) {
	requested := text(decl[sourceField])
	if c.supplied != nil && !strings.HasPrefix(requested, localImportPrefix) && requested != "" {
		return nil, importError("source-refused")
	}
	seen := map[string]bool{}
	for strings.HasPrefix(requested, "locked:") {
		if lock == nil {
			return nil, importError("lock-missing")
		}
		if seen[requested] {
			return nil, importError("cycle")
		}
		if err := c.budget.CheckDepth(len(seen) + 1); err != nil {
			return nil, err
		}
		seen[requested] = true
		record := lockedRecord(lock.records, strings.TrimPrefix(requested, "locked:"))
		if record == nil {
			return nil, importError("lock-record-missing")
		}
		resolved := map[string]any{sourceField: record[sourceField], namespaceField: decl[namespaceField], "version": record[requestedVersionField], "parameters": decl["parameters"], "digest": decl["digest"]}
		if text(resolved["digest"]) == "" {
			resolved["digest"] = record[contentDigestField]
		}
		if _, err := versionSpec(text(resolved["version"])); err != nil {
			return nil, importError(lockInvalidCode)
		}
		decl, requested = resolved, text(resolved[sourceField])
	}
	return decl, nil
}
func lockedRecord(records []map[string]any, reference string) map[string]any {
	for _, record := range records {
		if record[sourceField] == reference || record[resolvedSourceField] == reference {
			return record
		}
	}
	return nil
}
