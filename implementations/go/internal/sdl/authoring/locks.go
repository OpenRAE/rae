package authoring

import (
	"errors"
	"io/fs"
	"path"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type lockfile struct{ records []map[string]any }

func strictPin(pin string) bool {
	return len(pin) == 71 && strings.HasPrefix(pin, "sha256:") && strings.IndexFunc(pin[7:], func(r rune) bool { return !(r >= '0' && r <= '9' || r >= 'a' && r <= 'f') }) < 0
}
func pinMatches(raw []byte, pin string) bool {
	return pin == "" || strings.TrimPrefix(pin, "sha256:") == strings.TrimPrefix(digest.SHA256(raw), "sha256:")
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
	_, err := fs.Stat(c.request.FS, name)
	if errors.Is(err, fs.ErrNotExist) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, importError("source-unreadable")
	}
	raw, err := c.read(name)
	return raw, err == nil, err
}
func (c *composition) lock(importer string, needed bool) (*lockfile, error) {
	if !needed {
		return nil, nil
	}
	raw, present, err := c.optional(path.Join(path.Dir(importer), "raes.lock.json"))
	if err != nil || !present {
		return nil, err
	}
	if err = c.budget.AddBytes(int64(len(raw))); err != nil {
		return nil, err
	}
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(c.parser.limits.MaxInputBytes), MaxDepth: 8}, ingress.Object)
	if err != nil {
		return nil, importError("lock-invalid")
	}
	value := object(decoded)
	if !closed(value, nil, []string{"schema_version", "imports"}) {
		return nil, importError("lock-invalid")
	}
	if version, ok := value["schema_version"]; ok && version != "raes-lock/v1" {
		return nil, importError("lock-invalid")
	}
	rows, ok := value["imports"].([]any)
	if _, present = value["imports"]; present && !ok {
		return nil, importError("lock-invalid")
	}
	lock := &lockfile{}
	for _, raw := range rows {
		record := object(raw)
		if !closed(record, []string{"source", "namespace", "resolved_source", "module_id", "module_version", "manifest_digest", "content_digest", "export_hash"}, []string{"requested_version", "signer_id"}) {
			return nil, importError("lock-invalid")
		}
		for _, v := range record {
			if _, ok := v.(string); !ok {
				return nil, importError("lock-invalid")
			}
		}
		if _, ok := record["requested_version"]; !ok {
			record["requested_version"] = "*"
		}
		if _, ok := record["signer_id"]; !ok {
			record["signer_id"] = ""
		}
		lock.records = append(lock.records, record)
	}
	return lock, nil
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
	if lock == nil {
		if c.supplied != nil {
			return importError("lock-missing")
		}
		return nil
	}
	version := text(decl["version"])
	if version == "" {
		version = "*"
	}
	matches := []map[string]any{}
	for _, record := range lock.records {
		if record["source"] == requested && record["namespace"] == decl["namespace"] && record["requested_version"] == version {
			matches = append(matches, record)
		}
	}
	if len(matches) == 0 {
		if c.supplied != nil {
			return importError("lock-record-missing")
		}
		return nil
	}
	if c.supplied != nil && len(matches) != 1 {
		return importError("lock-ambiguous")
	}
	record := matches[0]
	if c.supplied == nil {
		if !pinMatches(raw, text(record["content_digest"])) {
			return importError("digest-mismatch")
		}
		return nil
	}
	exports := descriptor["exports"]
	if exports == nil {
		exports = map[string]any{}
	}
	encoded, err := toJSON(exports)
	if err != nil {
		return err
	}
	canonical, err := canonjson.Sorted(encoded, true)
	if err != nil {
		return err
	}
	expected := map[string]any{"resolved_source": path.Clean(strings.ReplaceAll(relative, "\\", "/")), "module_id": descriptor["id"], "module_version": descriptor["version"], "content_digest": digest.SHA256(raw), "export_hash": strings.TrimPrefix(digest.SHA256(canonical), "sha256:"), "manifest_digest": "", "signer_id": ""}
	for key, want := range expected {
		if record[key] != want {
			return importError("lock-mismatch")
		}
	}
	return nil
}
func (c *composition) trust(importer string, needed bool) error {
	if !needed {
		return nil
	}
	raw, present, err := c.optional(path.Join(path.Dir(importer), "raes-trust.yaml"))
	if err != nil || !present {
		return err
	}
	options := source.DefaultOptions()
	options.KeyScope = "data"
	options.Limits = c.parser.limits
	options.RequireMapping = true
	document, err := source.Decode(raw, options)
	if err != nil {
		return importError("source-refused")
	}
	value := object(document.Value())
	if !closed(value, nil, []string{"schema_version", "allow_unsigned_local_sources", "registries"}) {
		return importError("source-refused")
	}
	if allowed, ok := value["allow_unsigned_local_sources"]; ok {
		normalized, err := normalizeBoolean(allowed, false)
		if err != nil {
			return importError("source-refused")
		}
		if normalized == false {
			return importError("local-disabled")
		}
	}
	return nil
}
