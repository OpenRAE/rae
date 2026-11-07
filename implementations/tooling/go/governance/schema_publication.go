package governance

import (
	"context"
	"fmt"
	"maps"
	"slices"
	"strings"
)

const schemaPublicationCheck = "schema-publication"
const publicationStable = "stable"

type publicationEntry struct {
	id, path, stability, digest string
	schema                      any
	lastChange                  *mapping
	valid                       bool
}

type publicationInspection struct {
	repository          *repository
	paths, seenPaths    map[string]bool
	ids                 map[string]bool
	previous            string
	entries             []publicationEntry
	messages            []string
	removalDescriptions map[string]*mapping
}

func (c *checker) schemaPublication(ctx context.Context, r *repository) (Report, error) {
	catalog, err := publicationCatalog(r)
	if err != nil {
		if publicationContentError(err) {
			return publicationReport(publicationProblems(err)), nil
		}
		return Report{}, err
	}
	s := publicationInspection{repository: r, paths: map[string]bool{}, seenPaths: map[string]bool{}, ids: map[string]bool{}}
	records, err := s.header(catalog)
	if err != nil {
		return Report{}, err
	}
	if len(records) == 0 {
		return publicationReport(s.messages), nil
	}
	for i, value := range records {
		if err := ctx.Err(); err != nil {
			return Report{}, err
		}
		if err := s.record(value, i); err != nil {
			return Report{}, err
		}
	}
	if err := s.inventory(catalog); err != nil {
		return Report{}, err
	}
	if len(s.messages) == 0 && c.request.BaseRevision != "" {
		if err := s.history(ctx, c.request.BaseRevision); err != nil {
			return Report{}, err
		}
	}
	return publicationReport(s.messages), nil
}

func publicationReport(messages []string) Report {
	findings := make([]Finding, len(messages))
	for i, message := range messages {
		findings[i] = finding(schemaPublicationCheck, message, "")
	}
	return finish(findings)
}

func publicationProblems(err error) []string {
	if group, ok := err.(interface{ Unwrap() []error }); ok {
		messages := []string{}
		for _, child := range group.Unwrap() {
			messages = append(messages, publicationProblems(child)...)
		}
		return messages
	}
	return []string{err.Error()}
}

func (s *publicationInspection) header(catalog *mapping) ([]any, error) {
	version := catalog.get("schema_version")
	if !yamlHashable(version) {
		return nil, policyInputError("schema publication schema_version must be a string")
	}
	if version != "schema-publication-manifest/v1" && version != "schema-publication-manifest/v2" {
		s.messages = append(s.messages, "schema manifest schema_version must be 'schema-publication-manifest/v2' or 'schema-publication-manifest/v1'")
	}
	if catalog.get("hash_algorithm") != sha256Algorithm {
		s.messages = append(s.messages, "schema manifest hash_algorithm must be 'sha256'")
	}
	records, _ := catalog.get("schemas").([]any)
	if len(records) == 0 {
		s.messages = append(s.messages, "schema manifest must define a non-empty schemas array")
	}
	return records, nil
}

func (s *publicationInspection) inventory(catalog *mapping) error {
	published, err := publicationSchemaPaths(s.repository)
	if err != nil {
		return err
	}
	for _, name := range slices.Sorted(maps.Keys(published)) {
		if !s.paths[name] {
			s.messages = append(s.messages, "schema manifest is missing published schema: "+name)
		}
	}
	for _, name := range slices.Sorted(maps.Keys(s.paths)) {
		if !published[name] {
			s.messages = append(s.messages, "schema manifest references unpublished schema: "+name)
		}
	}
	s.removalDescriptions = s.removals(catalog.get("removed_schemas"))
	for _, name := range slices.Sorted(maps.Keys(s.removalDescriptions)) {
		if s.paths[name] {
			s.messages = append(s.messages, "schema manifest removed_schemas tombstone "+name+" refers to a still-published schema")
		}
	}
	return nil
}

func (s *publicationInspection) removals(value any) map[string]*mapping {
	tombstones := map[string]*mapping{}
	if value == nil {
		return tombstones
	}
	rows, ok := value.([]any)
	if !ok {
		s.messages = append(s.messages, "schema manifest removed_schemas must be a JSON array")
		return tombstones
	}
	for i, row := range rows {
		item := object(row)
		if item == nil {
			s.messages = append(s.messages, fmt.Sprintf("schema manifest removed_schemas entry %d must be a JSON object", i))
			continue
		}
		name, _ := item.get("schema_path").(string)
		if name == "" {
			s.messages = append(s.messages, fmt.Sprintf("schema manifest removed_schemas entry %d schema_path must be a non-empty string", i))
			continue
		}
		if !nonemptyText(item.get("summary")) {
			s.messages = append(s.messages, "schema manifest removed_schemas entry "+name+" summary must be a non-empty string")
			continue
		}
		tombstones[name] = item
	}
	return tombstones
}

func publicationDigestShape(value string) bool {
	value = strings.TrimSuffix(value, "\n") // Python's fixed '$' accepts one final LF.
	return len(value) == 64 && strings.Trim(value, "0123456789abcdef") == ""
}
