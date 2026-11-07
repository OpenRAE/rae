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
	return s.recordContent(raw, entry)
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
	entry.digest, _ = raw.get("content_hash").(string)
	if !publicationDigestShape(entry.digest) {
		s.messages = append(s.messages, manifestEntryPrefix+entry.id+" content_hash must be a 64-character sha256 hex digest")
	}
	entry.valid = stable && publicationDigestShape(entry.digest)
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

func (s *publicationInspection) recordContent(raw *mapping, entry publicationEntry) error {
	if publicationDigestShape(entry.digest) {
		digest, err := publicationDigest(entry.schema)
		if err != nil {
			return err
		}
		if digest != entry.digest {
			s.messages = append(s.messages, manifestEntryPrefix+entry.id+" content_hash "+entry.digest+" does not match canonical schema hash "+digest)
		}
		if raw.has("last_change") {
			entry.lastChange = s.lastChange(entry, raw.get("last_change"))
		}
	}
	if entry.valid {
		s.entries = append(s.entries, entry)
	}
	return nil
}

func (s *publicationInspection) lastChange(entry publicationEntry, value any) *mapping {
	raw := object(value)
	prefix := manifestEntryPrefix + entry.id + " last_change"
	if raw == nil {
		s.messages = append(s.messages, prefix+" must be a JSON object")
		return nil
	}
	before := len(s.messages)
	if !nonemptyText(raw.get("summary")) {
		s.messages = append(s.messages, prefix+".summary must be a non-empty string")
	}
	digest, _ := raw.get("content_hash").(string)
	switch {
	case !publicationDigestShape(digest):
		s.messages = append(s.messages, prefix+".content_hash must be a 64-character sha256 hex digest")
	case digest != entry.digest:
		s.messages = append(s.messages, prefix+".content_hash "+digest+" does not match the schema content_hash "+entry.digest+"; record the ledger entry against the current schema content")
	}
	if len(s.messages) != before {
		return nil
	}
	return raw
}
