package governance

import (
	"encoding/json"
	"fmt"
	"math/big"
	"slices"
	"strings"
	"unicode/utf8"
)

const guidanceSources = "source_refs"

const guidancePath = "specs/agent-guidance/agent-guidance.yaml"

func guidanceFailure(rule, message string) Finding {
	return finding("agent-guidance-"+rule, message, guidancePath)
}

func agentGuidance(r *repository) []Finding {
	if !r.file(guidancePath) {
		return []Finding{guidanceFailure("missing", "missing "+guidancePath)}
	}
	text, err := r.text(guidancePath)
	if err != nil {
		return []Finding{guidanceFailure("parse", "failed to parse "+guidancePath+": the file cannot be read as UTF-8 text")}
	}
	value, err := yamlValue([]byte(text), false)
	if err != nil {
		return []Finding{guidanceFailure("parse", "failed to parse "+guidancePath+": "+yamlFailureText([]byte(text), err))}
	}
	raw, ok := value.(*mapping)
	if !ok {
		return []Finding{guidanceFailure("shape", guidancePath+" must be a YAML mapping at the top level")}
	}
	findings := guidanceTop(raw)
	return append(findings, guidanceEntries(raw.get("guidance"))...)
}

func guidanceTop(raw *mapping) []Finding {
	findings := []Finding{}
	for _, field := range []string{"profile", "version", requirementRefs, guidanceSources, "recommended_workflow", "guidance"} {
		if !raw.has(field) {
			findings = append(findings, guidanceFailure("field", "missing required top-level field: "+field))
		}
	}
	if raw.has("profile") && raw.get("profile") != "raes-agent-guidance" {
		findings = append(findings, guidanceFailure("profile", "profile must be 'raes-agent-guidance'; got "+pythonRepr(raw.get("profile"))))
	}
	if raw.has("version") && !guidanceVersion(raw.get("version")) {
		findings = append(findings, guidanceFailure("version", "version must be a positive integer"))
	}
	return append(findings, guidanceTopLists(raw)...)
}

func guidanceVersion(value any) bool {
	if v, ok := value.(bool); ok {
		return v
	}
	if v, ok := value.(json.Number); ok {
		integer, valid := new(big.Int).SetString(string(v), 10)
		return valid && integer.Sign() > 0
	}
	return false
}

func guidanceTopLists(raw *mapping) []Finding {
	findings := []Finding{}
	for _, field := range []string{requirementRefs, guidanceSources, "recommended_workflow"} {
		if _, valid := stringList(raw.get(field), true); raw.has(field) && !valid {
			findings = append(findings, guidanceFailure("field-type", field+" must be a list of non-empty strings"))
		}
	}
	if refs, valid := stringList(raw.get(requirementRefs), true); valid && !slices.Contains(refs, "AUT-811") {
		findings = append(findings, guidanceFailure("requirement-ref", "requirement_refs must include AUT-811"))
	}
	if _, valid := raw.get("guidance").(*mapping); raw.has("guidance") && !valid {
		findings = append(findings, guidanceFailure("field-type", "guidance must be a mapping"))
	}
	return findings
}

func guidanceEntries(value any) []Finding {
	guidance, ok := value.(*mapping)
	if !ok {
		return nil
	}
	findings := []Finding{}
	seen := map[string]bool{}
	for _, category := range []string{"scope_boundaries", "invariants", "review_priorities", "safe_operating_expectations"} {
		entries, ok := guidance.get(category).([]any)
		if !ok || len(entries) == 0 {
			findings = append(findings, guidanceFailure("category", "guidance."+category+" must be a non-empty list"))
			continue
		}
		for i, entry := range entries {
			findings = append(findings, guidanceEntry(category, i, entry, seen)...)
		}
	}
	return findings
}

func guidanceEntry(category string, index int, value any, seen map[string]bool) []Finding {
	location := fmt.Sprintf("guidance.%s[%d]", category, index)
	entry, ok := value.(*mapping)
	if !ok {
		return []Finding{guidanceFailure("entry-shape", location+" must be a mapping; got "+pythonType(value))}
	}
	findings := []Finding{}
	for _, field := range []string{"id", "audience", "surfaces", "statement", guidanceSources} {
		if !entry.has(field) {
			findings = append(findings, guidanceFailure("entry-field", location+" missing "+field))
		}
	}
	findings = append(findings, guidanceID(entry.get("id"), location, seen)...)
	label := category
	if truth(entry.get("id")) {
		label = pythonStr(entry.get("id"))
	}
	findings = append(findings, guidanceAudience(entry.get("audience"), label)...)
	return append(findings, guidanceEntryFields(entry, label)...)
}

func guidanceID(value any, location string, seen map[string]bool) []Finding {
	id, ok := value.(string)
	if !ok || id == "" {
		return []Finding{guidanceFailure("entry-id", location+".id must be a non-empty string")}
	}
	if seen[id] {
		return []Finding{guidanceFailure("entry-duplicate", "duplicate guidance id: "+id)}
	}
	seen[id] = true
	return nil
}

func guidanceAudience(value any, label string) []Finding {
	audience, valid := stringList(value, true)
	if !valid {
		return []Finding{guidanceFailure("entry-audience", label+" audience must be a string list")}
	}
	for _, item := range audience {
		if item != "contributor" && item != "operator" {
			return []Finding{guidanceFailure("entry-audience", label+" audience must be within ['contributor', 'operator']; got "+pythonRepr(audience))}
		}
	}
	return nil
}

func guidanceEntryFields(entry *mapping, label string) []Finding {
	findings := []Finding{}
	for _, field := range []string{"surfaces", guidanceSources} {
		if _, valid := stringList(entry.get(field), true); !valid {
			findings = append(findings, guidanceFailure("entry-field-type", label+" "+field+" must be a string list"))
		}
	}
	statement, ok := entry.get("statement").(string)
	if !ok || utf8.RuneCountInString(strings.TrimFunc(statement, pythonWhitespace)) < 20 {
		findings = append(findings, guidanceFailure("entry-statement", label+" statement must be a substantive string"))
	}
	return findings
}
