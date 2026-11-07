package governance

import (
	"errors"
	"fmt"
	"slices"
	"strings"
)

const deprecationPath = "specs/evolution/deprecation-records.yaml"
const requirementRefs = "requirement_refs"

func deprecationFailure(rule, message string) Finding {
	return finding("deprecation-records-"+rule, message, deprecationPath)
}

func deprecation(r *repository) ([]Finding, error) {
	if !r.file(deprecationPath) {
		return []Finding{deprecationFailure("missing", "deprecation records surface not found: "+deprecationPath)}, nil
	}
	text, err := r.text(deprecationPath)
	if err != nil {
		if !errors.Is(err, errNotUTF8) {
			return nil, err
		}
		return []Finding{deprecationFailure("parse", "failed to parse "+deprecationPath)}, nil
	}
	value, err := yamlValue([]byte(text), false)
	if err != nil {
		message := "failed to parse " + deprecationPath
		if _, syntax := errors.AsType[*yamlSyntaxError](err); syntax {
			message += ": " + yamlFailureText([]byte(text), err)
		}
		return []Finding{deprecationFailure("parse", message)}, nil
	}
	raw, ok := value.(*mapping)
	if !ok {
		return []Finding{deprecationFailure("shape", deprecationPath+" must be a YAML mapping at the top level")}, nil
	}
	findings := deprecationTop(raw)
	if spec, ok := raw.get("spec").(string); ok && nonemptyText(spec) && !r.file(spec) {
		findings = append(findings, deprecationFailure("spec-missing", "spec path "+pythonRepr(spec)+" does not exist on disk"))
	}
	return append(findings, deprecationRecords(r, raw)...), nil
}

func deprecationTop(raw *mapping) []Finding {
	findings := []Finding{}
	for _, field := range []string{policyField, requirementRefs, adrRefsField, "spec", "records"} {
		if !raw.has(field) {
			findings = append(findings, deprecationFailure("field", "required top-level field is missing: "+field))
		}
	}
	if value := raw.get(policyField); raw.has(policyField) {
		if _, ok := value.(string); !ok {
			findings = append(findings, deprecationFailure("field-type", "policy must be a string; got "+pythonType(value)))
		} else if value != "ecosystem-deprecation-records" {
			findings = append(findings, deprecationFailure("policy-value", "policy must equal 'ecosystem-deprecation-records'; got "+pythonRepr(value)))
		}
	}
	findings = append(findings, deprecationRefs(raw, requirementRefs, "GOV-902", "requirement-ref")...)
	findings = append(findings, deprecationRefs(raw, adrRefsField, "ADR-075", "adr-ref")...)
	if raw.has("spec") && !nonemptyText(raw.get("spec")) {
		findings = append(findings, deprecationFailure("field-type", "spec must be a non-empty string path"))
	}
	if _, ok := raw.get("records").([]any); raw.has("records") && !ok {
		findings = append(findings, deprecationFailure("field-type", "records must be a list; got "+pythonType(raw.get("records"))))
	}
	return findings
}

func deprecationRefs(raw *mapping, field, required, rule string) []Finding {
	refs, valid := stringList(raw.get(field), false)
	if raw.has(field) && !valid {
		return []Finding{deprecationFailure("field-type", field+" must be a list of strings")}
	}
	if valid && !slices.Contains(refs, required) {
		return []Finding{deprecationFailure(rule, field+" must include "+required+"; got "+pythonRepr(refs))}
	}
	return nil
}

func deprecationRecords(r *repository, raw *mapping) []Finding {
	findings := []Finding{}
	seen := map[string]bool{}
	if records, ok := raw.get("records").([]any); ok {
		removed := publicationRemovedPaths(r)
		for i, value := range records {
			findings = append(findings, deprecationRecord(value, i, seen, removed)...)
		}
	}
	for _, id := range []string{"legacy-python-distribution", "sdl-domain-classification-fields", "sdl-import-path-field"} {
		if !seen[id] {
			findings = append(findings, deprecationFailure("canonical-record-missing", "the canonical deprecation record "+pythonRepr(id)+" is missing; established lifecycle records may not be removed from the ledger (retiring one is a deliberate edit to CANONICAL_DEPRECATION_RECORD_IDS)"))
		}
	}
	return findings
}

func deprecationRecord(value any, index int, seen map[string]bool, removed []string) []Finding {
	location := fmt.Sprintf("records[%d]", index)
	entry, ok := value.(*mapping)
	if !ok {
		return []Finding{deprecationFailure("entry-field", location+" must be a mapping; got "+pythonType(value))}
	}
	findings := []Finding{}
	for _, field := range []string{"id", "surface_class", "identifier", "status", "first_notice", "migration_reference", "notice_window", "verification_evidence"} {
		if !entry.has(field) {
			findings = append(findings, deprecationFailure("entry-field", location+" is missing required field: "+field))
		} else if !nonemptyText(entry.get(field)) {
			findings = append(findings, deprecationFailure("entry-field", location+"."+field+" must be a non-empty string"))
		}
	}
	if nonemptyText(entry.get("replacement")) == nonemptyText(entry.get("no_replacement_rationale")) {
		findings = append(findings, deprecationFailure("replacement", location+" must name exactly one of 'replacement' or 'no_replacement_rationale'"))
	}
	if id, ok := entry.get("id").(string); ok && nonemptyText(id) {
		if seen[id] {
			findings = append(findings, deprecationFailure("entry-duplicate", location+".id "+pythonRepr(id)+" is duplicated"))
		}
		seen[id] = true
	}
	findings = append(findings, deprecationEnums(entry, location)...)
	findings = append(findings, deprecationException(entry, location)...)
	if entry.get("status") == "removed" {
		findings = append(findings, deprecationRemoval(entry, location, removed)...)
	}
	return findings
}

func deprecationEnums(entry *mapping, location string) []Finding {
	findings := []Finding{}
	surfaces := []string{"adr", "apparatus-identity", "closed-contract-dto", "experiment-artifact", "ground-control-requirement", "processor-backend-support", "published-json-schema", "python-distribution", "sdl-scenario-module"}
	if surface, ok := entry.get("surface_class").(string); ok && nonemptyText(surface) && !slices.Contains(surfaces, surface) {
		findings = append(findings, deprecationFailure("surface-class", location+".surface_class "+pythonRepr(surface)+" is not a recognised surface class; expected one of "+pythonRepr(surfaces)))
	}
	statuses := []string{deprecatedStatus, "removed"}
	if status, ok := entry.get("status").(string); ok && nonemptyText(status) && !slices.Contains(statuses, status) {
		findings = append(findings, deprecationFailure("status", location+".status "+pythonRepr(status)+" must be one of "+pythonRepr(statuses)))
	}
	return findings
}

func deprecationException(entry *mapping, location string) []Finding {
	value := entry.get("security_exception")
	if value == nil {
		return nil
	}
	exception, ok := value.(*mapping)
	if !ok {
		return []Finding{deprecationFailure("security-exception", location+".security_exception must be a mapping when present")}
	}
	findings := []Finding{}
	for _, field := range []string{"affected_versions", "impact", "mitigation", "migration", "review_authority"} {
		if !nonemptyText(exception.get(field)) {
			findings = append(findings, deprecationFailure("security-exception", location+".security_exception must name a non-empty "+pythonRepr(field)+" (affected versions, impact, mitigation, migration, and review authority)"))
		}
	}
	return findings
}

func deprecationRemoval(entry *mapping, location string, removed []string) []Finding {
	findings := []Finding{}
	if !nonemptyText(entry.get("removal_record")) {
		findings = append(findings, deprecationFailure("removal-record", location+" has status 'removed' but no non-empty 'removal_record' (removal is allowed only after a complete deprecation record reaches its removal-eligibility rule)"))
	}
	if entry.get("surface_class") != "published-json-schema" {
		return findings
	}
	tombstone, _ := entry.get("removal_tombstone").(string)
	if !nonemptyText(tombstone) {
		findings = append(findings, deprecationFailure("removal-tombstone", location+" removes a published-json-schema surface and must name a 'removal_tombstone' schema_path recorded in the schema publication manifest"))
	} else if !slices.Contains(removed, tombstone) {
		findings = append(findings, deprecationFailure("removal-tombstone", location+".removal_tombstone "+pythonRepr(tombstone)+" is not a removed_schemas tombstone in "+publicationManifest+" (ADR-061 governs published-schema removal)"))
	}
	return findings
}

func nonemptyText(value any) bool {
	text, ok := value.(string)
	return ok && strings.TrimFunc(text, pythonWhitespace) != ""
}
