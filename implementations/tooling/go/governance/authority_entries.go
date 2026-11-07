package governance

import (
	"slices"
	"strconv"
	"strings"
)

const duplicateAuthoritySuffix = "' is duplicated"
const actualValueSeparator = "; got "

func boundaryEntry(value any, prefix string, fields []string, artifact bool) (*mapping, []Finding) {
	rule := "entry-field"
	if artifact {
		rule = "artifact-family-entry-field"
	}
	entry := object(value)
	if entry == nil {
		return nil, []Finding{boundaryFailure(rule, prefix+" must be a mapping; got "+pythonType(value))}
	}
	findings := []Finding{}
	for _, field := range fields {
		message := ""
		if !entry.has(field) {
			message = prefix + " is missing required field: " + field
		} else if text, ok := entry.get(field).(string); !ok || text == "" {
			message = prefix + "." + field + " must be a non-empty string"
		}
		if message != "" {
			findings = append(findings, boundaryFailure(rule, message))
		}
	}
	if artifact && entry.has(requirementRefs) {
		if _, ok := stringList(entry.get(requirementRefs), false); !ok {
			findings = append(findings, boundaryFailure(rule, prefix+".requirement_refs must be a list of strings"))
		}
	}
	if len(findings) > 0 {
		return nil, findings
	}
	return entry, findings
}

func boundaryRoots(raw *mapping, section string, normative bool) ([]boundaryRoot, []Finding) {
	entries, ok := raw.get(section).([]any)
	if !ok {
		return []boundaryRoot{}, []Finding{}
	}
	fields := []string{"id", "root", "note"}
	if normative {
		fields = []string{"id", "root", authorityField, "family"}
	}
	roots := []boundaryRoot{}
	findings := []Finding{}
	ids, paths := map[string]bool{}, map[string]bool{}
	for i, value := range entries {
		prefix := section + "[" + strconv.Itoa(i) + "]"
		entry, problems := boundaryEntry(value, prefix, fields, false)
		findings = append(findings, problems...)
		if entry == nil {
			continue
		}
		row := boundaryRoot{pythonStr(entry.get("id")), pythonStr(entry.get("root")), ""}
		if normative {
			row.family = pythonStr(entry.get("family"))
		}
		if reason := boundaryPathShape(row.root, true); reason != "" {
			findings = append(findings, boundaryFailure("root-shape", prefix+".root "+reason))
			continue
		}
		if ids[row.id] {
			findings = append(findings, boundaryFailure("entry-duplicate", prefix+".id '"+row.id+duplicateAuthoritySuffix))
			continue
		}
		if paths[row.root] {
			findings = append(findings, boundaryFailure("entry-duplicate", prefix+".root '"+row.root+duplicateAuthoritySuffix))
			continue
		}
		ids[row.id], paths[row.root] = true, true
		roots = append(roots, row)
	}
	return roots, append(findings, boundaryRootBindings(section, roots, normative)...)
}

func boundaryRootBindings(section string, roots []boundaryRoot, normative bool) []Finding {
	findings := []Finding{}
	for _, expected := range boundaryCanonicalRoots(normative) {
		i := slices.IndexFunc(roots, func(row boundaryRoot) bool { return row.id == expected.id })
		if i < 0 {
			findings = append(findings, boundaryFailure("canonical-root-missing", section+" is missing canonical entry: "+expected.id))
			continue
		}
		actual := roots[i]
		if actual.root != expected.root {
			findings = append(findings, boundaryFailure("canonical-root-binding", section+" entry '"+expected.id+"' must declare root="+pythonRepr(expected.root)+actualValueSeparator+pythonRepr(actual.root)))
		}
		if normative && actual.family != expected.family {
			findings = append(findings, boundaryFailure("canonical-root-binding", section+" entry '"+expected.id+"' must declare family="+pythonRepr(expected.family)+actualValueSeparator+pythonRepr(actual.family)))
		}
	}
	return findings
}

func boundaryArtifactFamilies(r *repository, raw *mapping, normative, consumers []boundaryRoot) []Finding {
	entries, ok := raw.get("normative_artifact_families").([]any)
	if !ok {
		return []Finding{}
	}
	findings := []Finding{}
	seen := map[string]bool{}
	accepted := map[string]string{}
	for i, value := range entries {
		prefix := "normative_artifact_families[" + strconv.Itoa(i) + "]"
		entry, problems := boundaryEntry(value, prefix, []string{"id", "artifact", authorityField, "family"}, true)
		findings = append(findings, problems...)
		if entry == nil {
			continue
		}
		id := pythonStr(entry.get("id"))
		if seen[id] {
			findings = append(findings, boundaryFailure("artifact-family-duplicate", prefix+".id '"+id+duplicateAuthoritySuffix))
		}
		seen[id] = true
		artifact := pythonStr(entry.get("artifact"))
		if issue := boundaryArtifactPath(r, prefix, artifact, normative, consumers); issue != nil {
			findings = append(findings, *issue)
			continue
		}
		accepted[artifact] = pythonStr(entry.get("family"))
	}
	for _, expected := range [][2]string{{guidancePath, "governance-guidance"}, {"specs/evolution/deprecation-records.yaml", "deprecation-records"}} {
		actual, found := accepted[expected[0]]
		if !found {
			findings = append(findings, boundaryFailure("artifact-family-canonical-missing", "normative_artifact_families is missing the canonical classification for "+expected[0]+" (expected family "+pythonRepr(expected[1])+")"))
		} else if actual != expected[1] {
			findings = append(findings, boundaryFailure("artifact-family-canonical-binding", "normative_artifact_families entry for "+expected[0]+" must declare family="+pythonRepr(expected[1])+actualValueSeparator+pythonRepr(actual)))
		}
	}
	return findings
}

func boundaryArtifactPath(r *repository, prefix, artifact string, normative, consumers []boundaryRoot) *Finding {
	rule, message := "", ""
	switch {
	case boundaryPathShape(artifact, false) != "":
		rule, message = "artifact-family-path-shape", prefix+".artifact "+boundaryPathShape(artifact, false)
	case !boundaryUnderRoots(artifact, normative):
		detail := "is not under any declared normative authority root"
		if boundaryUnderRoots(artifact, consumers) {
			detail = "is under a non-normative root"
		}
		rule, message = "artifact-family-non-normative", prefix+".artifact '"+artifact+"' "+detail
	case !r.file(artifact):
		rule, message = "artifact-family-missing", prefix+".artifact '"+artifact+"' does not exist on disk"
	}
	if rule == "" {
		return nil
	}
	result := boundaryFailure(rule, message)
	return &result
}
func boundaryUnderRoots(name string, roots []boundaryRoot) bool {
	return slices.ContainsFunc(roots, func(row boundaryRoot) bool { return strings.HasPrefix(name, row.root) })
}
