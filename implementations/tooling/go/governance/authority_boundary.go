package governance

import (
	"errors"
	"slices"
	"strings"
)

const boundaryPolicy = "specs/authority/authority-boundary.yaml"
const boundaryADR = adrDirectory + "/adr-009-normative-artifact-authority-and-repository-structure.md"
const boundarySeamADR = adrDirectory + "/adr-019-normative-authority-boundary-manifest.md"

type boundaryRoot struct{ id, root, family string }

func boundaryCanonicalRoots(normative bool) []boundaryRoot {
	if normative {
		return []boundaryRoot{
			{"normative_prose", "specs/", "prose"},
			{"normative_schemas", "contracts/schemas/", "schemas"},
			{"normative_fixtures", "contracts/fixtures/", "fixtures"},
			{"normative_profiles", "contracts/profiles/", "profiles"},
			{"normative_realization_envelopes", "contracts/realization-envelopes/", "realization-envelopes"},
			{"normative_concept_authority", "contracts/concept-authority/", "concept-authority"},
			{"normative_provenance", "contracts/provenance/", provenanceField},
		}
	}
	return []boundaryRoot{
		{"reference_implementations", "implementations/", ""}, {"explanatory_docs", "docs/", ""},
		{"worked_examples", "examples/", ""}, {"research_notes", "research/", ""},
		{"process_notes", "notes/", ""}, {"tooling", "tools/", ""},
	}
}

func boundaryFailure(rule, message string) Finding {
	return finding("authority-boundary-"+rule, message, boundaryPolicy)
}

func (c *checker) authorityBoundary(r *repository) (Report, error) {
	if !r.file(boundaryPolicy) {
		return c.finish(r, []Finding{boundaryFailure("missing", "authority boundary policy not found: "+boundaryPolicy)})
	}
	text, err := r.text(boundaryPolicy)
	if err != nil {
		if !errors.Is(err, errNotUTF8) {
			return Report{}, err
		}
		return c.finish(r, []Finding{boundaryFailure("parse", "failed to parse "+boundaryPolicy)})
	}
	value, err := yamlValue([]byte(text), false)
	if err != nil {
		return c.finish(r, []Finding{boundaryFailure("parse", "failed to parse "+boundaryPolicy+": "+yamlFailureText([]byte(text), err))})
	}
	raw := object(value)
	if raw == nil {
		return c.finish(r, []Finding{boundaryFailure("shape", boundaryPolicy+" must be a YAML mapping at the top level")})
	}
	findings := boundaryTop(raw)
	findings = append(findings, boundaryReferences(raw)...)
	normative, rootFindings := boundaryRoots(raw, "authority_roots", true)
	findings = append(findings, rootFindings...)
	consumers, consumerFindings := boundaryRoots(raw, "non_normative_roots", false)
	findings = append(findings, consumerFindings...)
	findings = append(findings, boundarySchemaBlock(object(raw.get("schema_authority")))...)
	findings = append(findings, boundaryArtifactFamilies(r, raw, normative, consumers)...)
	legacy, _ := stringList(raw.get("legacy_top_level_dirs"), false)
	missing := []string{}
	for _, name := range []string{"schemas", "conformance", "src"} {
		if !slices.Contains(legacy, name) {
			missing = append(missing, name)
		}
	}
	slices.Sort(missing)
	if len(missing) > 0 {
		findings = append(findings, boundaryFailure("legacy-floor", "legacy_top_level_dirs must include the ADR-009 floor ['schemas', 'conformance', 'src']; missing "+pythonRepr(missing)))
	}
	findings = append(findings, boundaryOverlap(normative, consumers, legacy)...)
	disk, diskErr := boundaryDisk(r, normative, consumers, legacy)
	if diskErr != nil {
		return Report{}, diskErr
	}
	findings = append(findings, disk...)
	findings = append(findings, boundaryMisplacedSchemas(r, object(raw.get("schema_authority")))...)
	if !r.file(publicationManifest) {
		findings = append(findings, finding("authority-boundary-publication-manifest-missing", "schema publication manifest '"+publicationManifest+"' is missing", publicationManifest))
	}
	findings = append(findings, boundaryADRDrift(r, normative)...)
	findings = append(findings, boundaryReadmeDrift(r, "contracts/README.md", "contracts")...)
	findings = append(findings, boundaryReadmeDrift(r, "specs/README.md", "specs")...)
	return c.finish(r, findings)
}

func boundaryTop(raw *mapping) []Finding {
	fields := []string{policyField, requirementRefs, adrRefsField, "authority_roots", "non_normative_roots", "legacy_top_level_dirs", "schema_authority", "normative_artifact_families"}
	findings := []Finding{}
	for _, field := range fields {
		if !raw.has(field) {
			findings = append(findings, boundaryFailure("field", "required top-level field is missing: "+field))
		}
	}
	if _, ok := raw.get(policyField).(string); raw.has(policyField) && !ok {
		findings = append(findings, boundaryFailure("field-type", "policy must be a string; got "+pythonType(raw.get(policyField))))
	}
	for _, field := range fields[1:] {
		if !raw.has(field) {
			continue
		}
		message := boundaryTopType(field, raw.get(field))
		if message != "" {
			findings = append(findings, boundaryFailure("field-type", message))
		}
	}
	return findings
}

func boundaryTopType(field string, value any) string {
	message := ""
	switch field {
	case requirementRefs, adrRefsField, "legacy_top_level_dirs":
		if _, ok := stringList(value, false); !ok {
			message = field + " must be a list of strings"
		}
	case "schema_authority":
		if object(value) == nil {
			message = field + " must be a mapping; got " + pythonType(value)
		}
	default:
		if _, ok := value.([]any); !ok {
			message = field + " must be a list; got " + pythonType(value)
		}
	}
	return message
}

func boundaryReferences(raw *mapping) []Finding {
	findings := []Finding{}
	if refs, ok := stringList(raw.get(requirementRefs), false); ok && !slices.Contains(refs, "ASR-517") {
		findings = append(findings, boundaryFailure("requirement-ref", "requirement_refs must include ASR-517; got "+pythonRepr(refs)))
	}
	if refs, ok := stringList(raw.get(adrRefsField), false); ok {
		for _, ref := range []string{"ADR-009", "ADR-019"} {
			if !slices.Contains(refs, ref) {
				findings = append(findings, boundaryFailure("adr-ref", "adr_refs must include "+ref+"; got "+pythonRepr(refs)))
			}
		}
	}
	if value, ok := raw.get(policyField).(string); ok && value != "normative-artifact-authority" {
		findings = append(findings, boundaryFailure("value", "policy must equal 'normative-artifact-authority'; got "+pythonRepr(value)))
	}
	return findings
}

func boundaryPathShape(name string, directory bool) string {
	if secretPath(name) {
		return "must not name a protected path; got " + pythonRepr(name)
	}
	if name == "" {
		return "must be a non-empty string"
	}
	if strings.HasPrefix(name, "/") {
		return "must be a repo-relative path; got " + pythonRepr(name)
	}
	if slices.Contains(strings.Split(name, "/"), "..") {
		return "must not traverse parent directories; got " + pythonRepr(name)
	}
	if directory && !strings.HasSuffix(name, "/") {
		return "must end with '/'; got " + pythonRepr(name)
	}
	if !directory && strings.HasSuffix(name, "/") {
		return "must be a file path, not a directory; got " + pythonRepr(name)
	}
	return ""
}
