package governance

import (
	"fmt"
	"strings"
)

const manifestEntryPrefix = "schema manifest entry "

func (s *publicationInspection) record(value any, index int) error {
	raw := object(value)
	if raw == nil {
		s.messages = append(s.messages, fmt.Sprintf("schema manifest entry %d must be an object", index))
		return nil
	}
	entry, proceed, err := s.recordHeader(raw, index)
	if err != nil || !proceed {
		return err
	}
	resolved, ok := s.schemaPath(entry.path)
	if !ok {
		return nil
	}
	s.paths[entry.path] = true
	if !s.repository.file(resolved) {
		s.messages = append(s.messages, "schema manifest path does not exist: "+entry.path)
		return nil
	}
	if stem := pythonPathStem(resolved); stem != entry.id {
		s.messages = append(s.messages, "schema manifest contract_id "+pythonRepr(entry.id)+" must match schema filename "+pythonRepr(stem))
	}
	text, err := s.repository.text(resolved)
	if err != nil {
		return err
	}
	schema, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		s.messages = append(s.messages, "schema manifest path is not valid JSON: "+entry.path+": "+err.Error())
		return nil //nolint:nilerr // Syntax failures are ordered publication findings.
	}
	entry.schema = schema
	if entry.valid {
		s.entries = append(s.entries, entry)
	}
	return nil
}

func (s *publicationInspection) recordHeader(raw *mapping, index int) (publicationEntry, bool, error) {
	entry := publicationEntry{}
	entry.id, _ = raw.get("contract_id").(string)
	if entry.id == "" {
		s.messages = append(s.messages, fmt.Sprintf("schema manifest entry %d contract_id must be a non-empty string", index))
		return entry, false, nil
	}
	entry.path, _ = raw.get("schema_path").(string)
	if entry.path == "" {
		s.messages = append(s.messages, manifestEntryPrefix+entry.id+" schema_path must be a non-empty string")
		return entry, false, nil
	}
	if !yamlHashable(raw.get("stability")) {
		return entry, false, policyInputError("schema publication stability must be draft or stable")
	}
	entry.stability, _ = raw.get("stability").(string)
	stable := entry.stability == "draft" || entry.stability == publicationStable
	if !stable {
		s.messages = append(s.messages, manifestEntryPrefix+entry.id+" stability must be one of: draft, stable")
	}
	for _, key := range retiredEntryKeys {
		if raw.has(key) {
			s.messages = append(s.messages, manifestEntryPrefix+entry.id+" must not record "+key+"; git holds schema history")
		}
	}
	entry.valid = stable
	s.recordIdentity(entry)
	return entry, true, nil
}

func (s *publicationInspection) recordIdentity(entry publicationEntry) {
	if entry.id <= s.previous {
		s.messages = append(s.messages, "schema manifest entries must be sorted by contract_id")
	}
	s.previous = entry.id
	if s.ids[entry.id] {
		s.messages = append(s.messages, "schema manifest contains duplicate contract_id: "+entry.id)
	}
	s.ids[entry.id] = true
	if s.seenPaths[entry.path] {
		s.messages = append(s.messages, "schema manifest contains duplicate schema_path: "+entry.path)
	}
	s.seenPaths[entry.path] = true
}

func (s *publicationInspection) schemaPath(name string) (string, bool) {
	switch {
	case name != prefixPath(name) || strings.HasPrefix(name, "/") || strings.HasPrefix(name, "../"):
		s.messages = append(s.messages, "schema manifest path must be a normalized repo-relative path: "+name)
	case !strings.HasPrefix(name, schemasPrefix):
		s.messages = append(s.messages, "schema manifest path must be under contracts/schemas/: "+name)
	case !strings.HasSuffix(name, ".json"):
		s.messages = append(s.messages, "schema manifest path must point to a JSON schema file: "+name)
	default:
		resolved, err := publicationSchemaPath(s.repository, name)
		if err == nil {
			return resolved, true
		}
		s.messages = append(s.messages, "schema manifest path resolves outside contracts/schemas/: "+name)
	}
	return "", false
}
