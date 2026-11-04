package admission

import (
	"regexp"
	"strings"
)

func lineageLedger(v any) error {
	for _, pair := range [][2]string{{"citations", "citation_id"}, {"sources", "source_id"}, {"subjects", "subject_id"}, {"third_party_dispositions", "source_ref"}} {
		if len(rowSet(at(v, pair[0]), pair[1])) != len(array(at(v, pair[0]))) {
			return invalid()
		}
	}
	citations := rowSet(at(v, "citations"), "citation_id")
	sources, dispositions := map[string]any{}, map[string]any{}
	for _, source := range array(at(v, "sources")) {
		if !citations[stringAt(source, "citation_ref")] || lineageSource(source) != nil {
			return invalid()
		}
		sources[stringAt(source, "source_id")] = source
	}
	for _, disposition := range array(at(v, "third_party_dispositions")) {
		id := stringAt(disposition, "source_ref")
		if sources[id] == nil || (stringAt(disposition, "notice_decision") == "required_included") != (at(disposition, "notice_artifact") != nil) {
			return invalid()
		}
		dispositions[id] = disposition
	}
	for _, subject := range array(at(v, "subjects")) {
		if err := lineageSubject(subject, sources, citations, dispositions); err != nil {
			return err
		}
	}
	return nil
}

func lineageSubject(subject any, sources map[string]any, citations map[string]bool, dispositions map[string]any) error {
	prefix := map[string]string{"top_level_field": "sdl-field:", "runtime_family": "runtime-family:", "concept_family": "concept-family:", "reference_model": "reference-model:"}[stringAt(subject, "subject_kind")]
	if prefix == "" || !strings.HasPrefix(stringAt(subject, "subject_id"), prefix) {
		return invalid()
	}
	for _, claim := range array(at(subject, "claims")) {
		if err := lineageClaimDimensions(claim); err != nil {
			return err
		}
		if err := lineageClaimReferences(claim, sources, citations); err != nil {
			return err
		}
		if stringAt(subject, "disposition") == "planned" && (stringAt(claim, "compatibility") == "compatible" || stringAt(claim, "compatibility") == statusPartial) {
			return invalid()
		}
		if err := lineageArtifactClaim(claim, dispositions); err != nil {
			return err
		}
	}
	return nil
}

func lineageClaimDimensions(v any) error {
	if stringAt(v, "classification") == "raes_native" {
		return require(len(array(at(v, "source_refs"))) == 0 && len(array(at(v, "source_boundaries"))) == 0 && len(array(at(v, "internal_authority_refs"))) > 0 && stringAt(v, "compatibility") == termNotApplicable && stringAt(v, "compatibility_direction") == termNotApplicable)
	}
	if len(array(at(v, "source_refs"))) == 0 || len(array(at(v, "source_boundaries"))) == 0 || len(array(at(v, "citation_refs"))) == 0 || stringAt(v, "compatibility_direction") != "raes_relative_to_source" {
		return invalid()
	}
	switch stringAt(v, "classification") {
	case "adopted_syntax":
		return require(stringAt(v, "plane") == "syntax")
	case "adopted_semantics":
		return require(stringAt(v, "plane") == "semantics")
	default:
		return nil
	}
}

func lineageArtifactClaim(claim any, dispositions map[string]any) error {
	if stringAt(claim, "plane") != "artifact_code" {
		return nil
	}
	for _, source := range stringsOf(at(claim, "source_refs")) {
		disposition := dispositions[source]
		if disposition == nil || stringAt(disposition, "notice_decision") == statusUnknown || !subset(rowIDs(at(claim, "raes_boundaries"), "artifact"), rowSet(at(disposition, "derivation_scope"), "artifact")) {
			return invalid()
		}
	}
	return nil
}

func lineageClaimReferences(claim any, sources map[string]any, citations map[string]bool) error {
	expected := map[string]bool{}
	for _, source := range stringsOf(at(claim, "source_refs")) {
		if sources[source] == nil {
			return invalid()
		}
		expected[stringAt(sources[source], "citation_ref")] = true
	}
	if !subset(stringsOf(at(claim, "citation_refs")), citations) || !equalSet(set(at(claim, "citation_refs")), expected) {
		return invalid()
	}
	return nil
}

func lineageSource(v any) error {
	mutable := regexp.MustCompile(`(?i)\b(?:reviewed|capture)\b`).MatchString(stringAt(v, "version_or_edition"))
	floating := regexp.MustCompile(`/(?:blob|tree)/(?:main|master|latest)(?:/|$)`).MatchString(stringAt(v, "canonical_url"))
	if (mutable || floating) && at(v, "archival_capture") == nil {
		return invalid()
	}
	if stringAt(v, "kind") != "git" {
		return nil
	}
	commit := stringAt(v, "commit")
	return require(strings.Contains(stringAt(v, "canonical_url"), commit) && (at(v, "license_url") == nil || strings.Contains(stringAt(v, "license_url"), commit)))
}
