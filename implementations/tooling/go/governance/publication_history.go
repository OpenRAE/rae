package governance

import (
	"context"
	"errors"
	"maps"
	"slices"
	"strings"
)

func (s *publicationInspection) history(ctx context.Context, base string) error {
	if err := s.stableChanges(ctx, base); err != nil {
		return err
	}
	baseEntries, _, err := publicationBaseCatalog(ctx, s.repository, base)
	if err != nil {
		return err
	}
	if err := s.changeLedger(ctx, base); err != nil {
		return err
	}
	s.removalLedger(baseEntries)
	return nil
}

func (s *publicationInspection) stableChanges(ctx context.Context, base string) error {
	stable := []publicationEntry{}
	for _, entry := range s.entries {
		if entry.stability == publicationStable {
			stable = append(stable, entry)
		}
	}
	if len(stable) == 0 {
		return nil
	}
	baseEntries, problem, err := publicationBaseCatalog(ctx, s.repository, base)
	if err != nil {
		return err
	}
	if problem != "" {
		s.messages = append(s.messages, problem)
		return nil
	}
	for _, entry := range stable {
		previous := baseEntries[entry.id]
		if previous == nil || previous.get("stability") != publicationStable {
			continue
		}
		if err := s.stableEntry(ctx, base, previous, entry); err != nil {
			return err
		}
	}
	return nil
}

func (s *publicationInspection) stableEntry(ctx context.Context, base string, previous *mapping, entry publicationEntry) error {
	name, ok := previous.get("schema_path").(string)
	if !ok {
		return nil
	}
	if name != entry.path {
		s.messages = append(s.messages, "stable schema "+entry.id+" changed schema_path without a version bump: "+name+" -> "+entry.path)
		return nil
	}
	text, err := publicationGitText(ctx, s.repository, "show", "--end-of-options", base+":"+name)
	if err != nil {
		return err
	}
	if text == nil {
		s.messages = append(s.messages, "base schema for "+entry.id+" is missing at "+base+": "+name)
		return nil
	}
	value, err := decodeJSON([]byte(*text), 0, false)
	if err != nil {
		s.messages = append(s.messages, "base schema for "+entry.id+" at "+base+":"+name+" is not valid JSON")
		return nil //nolint:nilerr // Invalid historical JSON is a reference finding.
	}
	digest, err := publicationDigest(value)
	if err != nil || digest == entry.digest {
		return err
	}
	changes, err := publicationBreakingChanges(value, entry.schema)
	if err != nil {
		if _, depth := errors.AsType[publicationComparisonError](err); depth {
			s.messages = append(s.messages, "stable schema "+entry.id+" nests beyond the depth that the compatibility check can compare")
			return nil
		}
		return err
	}
	if len(changes) > 0 {
		s.messages = append(s.messages, "stable schema "+entry.id+" changed incompatibly without a version bump: "+strings.Join(changes, "; "))
	}
	return nil
}

func (s *publicationInspection) changeLedger(ctx context.Context, base string) error {
	for _, entry := range s.entries {
		unchanged, err := s.unchangedSchema(ctx, base, entry)
		if err != nil {
			return err
		}
		if !unchanged && entry.lastChange == nil {
			s.messages = append(s.messages, "published schema "+entry.id+" changed without a contract-facing change description; add a 'last_change' entry (summary + current content_hash) to its record under "+publicationEntries+" recording why the contract changed")
		}
	}
	return nil
}

func (s *publicationInspection) unchangedSchema(ctx context.Context, base string, entry publicationEntry) (bool, error) {
	text, err := publicationGitText(ctx, s.repository, "show", "--end-of-options", base+":"+entry.path)
	if err != nil || text == nil {
		return false, err
	}
	value, err := decodeJSON([]byte(*text), 0, false)
	if err != nil || value == nil {
		return false, nil //nolint:nilerr // Parse failure and JSON null both fail the reference's explicit non-None unchanged check.
	}
	digest, err := publicationDigest(value)
	return digest == entry.digest, err
}

func (s *publicationInspection) removalLedger(baseEntries map[string]*mapping) {
	basePaths, currentPaths := map[string]bool{}, map[string]bool{}
	for _, entry := range baseEntries {
		if name, ok := entry.get("schema_path").(string); ok && strings.HasPrefix(name, schemasPrefix) {
			basePaths[name] = true
		}
	}
	for _, entry := range s.entries {
		currentPaths[entry.path] = true
	}
	for _, name := range slices.Sorted(maps.Keys(basePaths)) {
		if !currentPaths[name] && s.removalDescriptions[name] == nil {
			s.messages = append(s.messages, "published schema "+name+" was removed without a contract-facing removal description; add a tombstone record (schema_path + summary) under "+publicationTombstones+" recording why the contract was removed")
		}
	}
}
