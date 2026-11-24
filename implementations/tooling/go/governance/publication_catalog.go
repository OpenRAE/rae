package governance

import (
	"errors"
	"io/fs"
	"path"
	"slices"
	"strings"
)

const publicationManifest = "contracts/schema-publication-manifest.json"
const publicationEntries = "contracts/schema-publication/entries"
const publicationTombstones = "contracts/schema-publication/tombstones"

// publicationCatalog normalizes the two existing storage layouts. It does not
// validate publication policy; consumers receive the candidate catalog as data.
func publicationCatalog(r *repository) (*mapping, error) {
	text, err := r.text(publicationManifest)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return nil, policyInputError("schema publication manifest is missing: " + publicationManifest)
		}
		return nil, err
	}
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return nil, policyInputError("schema publication manifest is not valid JSON: " + err.Error())
	}
	raw, ok := value.(*mapping)
	if !ok {
		return nil, policyInputError("schema publication manifest must be a JSON object")
	}
	if raw.get("schema_version") == "schema-publication-manifest/v1" {
		return raw, nil
	}
	if raw.size() != 4 || !raw.has("schema_version") || !raw.has("hash_algorithm") || !raw.has("entries_directory") || !raw.has("tombstones_directory") {
		return nil, policyInputError("schema publication manifest has invalid fields")
	}
	entries, entryErr := publicationRecords(r, raw.get("entries_directory"), publicationEntries, false)
	if entryErr != nil && !publicationContentError(entryErr) {
		return nil, entryErr
	}
	tombstones, tombstoneErr := publicationRecords(r, raw.get("tombstones_directory"), publicationTombstones, true)
	if tombstoneErr != nil && !publicationContentError(tombstoneErr) {
		return nil, tombstoneErr
	}
	if combined := errors.Join(entryErr, tombstoneErr); combined != nil {
		return nil, combined
	}
	result := newMapping()
	result.set("schema_version", raw.get("schema_version"))
	result.set("hash_algorithm", raw.get("hash_algorithm"))
	result.set("schemas", entries)
	result.set("removed_schemas", tombstones)
	return result, nil
}

func publicationRecords(r *repository, value any, directory string, tombstones bool) ([]any, error) {
	if value != directory {
		return nil, policyInputError("schema publication record directory is invalid: " + directory)
	}
	resolved, entries, err := publicationDirectory(r, directory)
	if err != nil {
		return nil, err
	}
	records := []any{}
	problems := []error{}
	for _, entry := range entries {
		if !strings.HasSuffix(entry.Name(), ".json") {
			continue
		}
		record, readErr := publicationRecord(r, path.Join(resolved, entry.Name()), tombstones)
		if readErr != nil {
			if !publicationContentError(readErr) {
				return nil, readErr
			}
			problems = append(problems, readErr)
			continue
		}
		records = append(records, record)
	}
	if len(records) == 0 && len(problems) == 0 && !tombstones {
		return nil, policyInputError("schema publication entry directory is empty")
	}
	return records, errors.Join(problems...)
}

func publicationDirectory(r *repository, directory string) (string, []fs.DirEntry, error) {
	resolved, err := r.resolve(directory)
	if err != nil {
		if errors.Is(err, errUnsafePath) {
			return "", nil, policyInputError("schema publication record directory resolves outside the repository")
		}
		return "", nil, err
	}
	info, err := r.root.Stat(resolved)
	if err != nil || !info.IsDir() {
		return "", nil, policyInputError("schema publication record directory is missing: " + directory)
	}
	// Path.glob suppresses enumeration errors after its is-directory check.
	// Individual record reads below retain their operational error behavior.
	entries, _ := fs.ReadDir(r.root.FS(), resolved)
	return resolved, entries, nil
}

func publicationContentError(err error) bool {
	_, ok := errors.AsType[policyInputError](err)
	return ok
}

func publicationRecord(r *repository, name string, tombstone bool) (*mapping, error) {
	text, err := r.text(name)
	if err != nil {
		return nil, err
	}
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return nil, policyInputError("schema publication record is not valid JSON: " + name + ": " + err.Error())
	}
	record, ok := value.(*mapping)
	if !ok {
		return nil, policyInputError("schema publication record must be a JSON object: " + name)
	}
	key := "contract_id"
	if tombstone {
		key = "schema_path"
	}
	identity, ok := record.get(key).(string)
	if !ok || pythonPathStem(name) != pythonPathStem(identity) {
		return nil, policyInputError("schema publication record filename does not match its identity: " + name)
	}
	return record, nil
}

// Python 3.14 treats a trailing dot as a suffix, but leading dots alone do not
// form one. Backslashes are ordinary filename characters on this platform.
func pythonPathStem(name string) string {
	parts := strings.Split(name, "/")
	name = ""
	for _, part := range slices.Backward(parts) {
		if part != "" && part != "." {
			name = part
			break
		}
	}
	index := strings.LastIndexByte(name, '.')
	if index > 0 && strings.Trim(name[:index], ".") != "" {
		return name[:index]
	}
	return name
}

func publicationRemovedPaths(r *repository) []string {
	catalog, err := publicationCatalog(r)
	if err != nil {
		return nil
	}
	entries, _ := catalog.get("removed_schemas").([]any)
	paths := []string{}
	for _, value := range entries {
		entry, ok := value.(*mapping)
		if !ok {
			continue
		}
		if name, ok := entry.get("schema_path").(string); ok && nonemptyText(name) {
			paths = append(paths, name)
		}
	}
	slices.Sort(paths)
	return slices.Compact(paths)
}
