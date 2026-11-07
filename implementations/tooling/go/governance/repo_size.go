package governance

import (
	"bytes"
	"context"
	"encoding/json"
	"math/big"
	"slices"
	"strconv"
	"strings"
)

type repoLayerRule struct{ id, root, forbidden string }
type repoSizePolicy struct {
	cap                         *big.Int
	capText, allowlist          string
	roots, extensions, excluded []string
}

func repoConfigFinding(message string) Finding {
	return finding("policy-config-malformed", message, repoPolicyConfig)
}

func repoLayerAndSize(ctx context.Context, r *repository, policy *mapping, changed []string) ([]Finding, error) {
	layers, findings := repoLayerConfig(policy.get("layering_rules"))
	size, problems := repoSizeConfig(policy.get("oversized_source_files"))
	findings = append(findings, problems...)
	if len(findings) > 0 {
		return findings, nil
	}
	findings, err := repoLayering(ctx, r, layers, changed)
	if err != nil {
		return nil, err
	}
	allowlist, problems := repoSizeAllowlist(r, size.allowlist)
	if len(problems) > 0 {
		return append(findings, problems...), nil
	}
	for _, name := range changed {
		if !repoSizeCandidate(name, size) || slices.Contains(allowlist, name) || !r.file(name) {
			continue
		}
		data, err := r.read(name)
		if err != nil {
			continue
		}
		count := repoByteLineCount(data)
		if new(big.Int).SetInt64(int64(count)).Cmp(size.cap) > 0 {
			findings = append(findings, finding("oversized-source-file", "file is "+strconv.Itoa(count)+" lines, exceeding the "+size.capText+"-line cap; split it into subdomain modules (do not add it to "+size.allowlist+"; the allowlist only shrinks)", name))
		}
	}
	// ADR-015's initial oversized-file set is empty after its current rebaseline.
	// Therefore every allowlist entry is an expansion of the locked empty set.
	for _, name := range allowlist {
		findings = append(findings, finding("oversized-allowlist-locked", "'"+name+"' is in "+size.allowlist+" but is not one of the files that were over the source-file cap when it was adopted (_ADR015_INITIAL_OVERSIZED_FILES in tools/policy/repo_policy.py); the allowlist may only shrink — split the file instead of adding it", size.allowlist))
	}
	return findings, nil
}

func repoLayerConfig(value any) ([]repoLayerRule, []Finding) {
	if value == nil {
		return nil, []Finding{repoConfigFinding("layering_rules is required (ADR-015) but is absent")}
	}
	entries, ok := value.([]any)
	if !ok {
		return nil, []Finding{repoConfigFinding("layering_rules must be a list; got " + pythonType(value))}
	}
	if len(entries) == 0 {
		return nil, []Finding{repoConfigFinding("layering_rules must contain at least one rule (ADR-015)")}
	}
	rules := []repoLayerRule{}
	findings := []Finding{}
	seen := map[string]bool{}
	for i, value := range entries {
		prefix := "layering_rules[" + strconv.Itoa(i) + "]"
		row := object(value)
		if row == nil {
			findings = append(findings, repoConfigFinding(prefix+" must be a mapping; got "+pythonType(value)))
			continue
		}
		problems := repoLayerFields(row, prefix, seen)
		findings = append(findings, problems...)
		if len(problems) > 0 {
			continue
		}
		rule := repoLayerRule{pythonStr(row.get("id")), pythonStr(row.get("scope_root")), pythonStr(row.get("forbidden_top_level"))}
		seen[rule.id] = true
		rules = append(rules, rule)
	}
	if len(findings) > 0 {
		return nil, findings
	}
	return rules, findings
}
func repoLayerFields(row *mapping, prefix string, seen map[string]bool) []Finding {
	findings := []Finding{}
	for _, field := range []string{"id", "scope_root", "forbidden_top_level"} {
		value, textual := row.get(field).(string)
		switch {
		case !textual || value == "":
			findings = append(findings, repoConfigFinding(prefix+"."+field+" must be a non-empty string; got "+pythonRepr(row.get(field))))
		case field == "id" && seen[value]:
			findings = append(findings, repoConfigFinding(prefix+".id '"+value+"' is duplicated"))
		}
	}
	return findings
}

func repoSizeConfig(value any) (repoSizePolicy, []Finding) {
	if value == nil {
		return repoSizePolicy{}, []Finding{repoConfigFinding("oversized_source_files block is required (ADR-015) but is absent")}
	}
	raw := object(value)
	if raw == nil {
		return repoSizePolicy{}, []Finding{repoConfigFinding("oversized_source_files must be a mapping; got " + pythonType(value))}
	}
	result := repoSizePolicy{}
	findings := []Finding{}
	if integer, ok := repoPositiveInteger(raw.get("line_cap")); ok {
		result.cap = integer
		result.capText = integer.String()
	} else {
		findings = append(findings, repoConfigFinding("oversized_source_files.line_cap must be a positive integer; got "+pythonRepr(raw.get("line_cap"))))
	}
	result.allowlist, _ = raw.get("allowlist_path").(string)
	if result.allowlist == "" {
		findings = append(findings, repoConfigFinding("oversized_source_files.allowlist_path must be a non-empty string; got "+pythonRepr(raw.get("allowlist_path"))))
	}
	for _, field := range []struct {
		name   string
		target *[]string
	}{{"scope_roots", &result.roots}, {"file_extensions", &result.extensions}} {
		values, ok := stringList(raw.get(field.name), false)
		if !ok || len(values) == 0 {
			findings = append(findings, repoConfigFinding("oversized_source_files."+field.name+" must be a non-empty list of strings"))
		} else {
			*field.target = values
		}
	}
	excluded := raw.get("excluded_path_prefixes")
	if excluded != nil {
		values, ok := stringList(excluded, false)
		if !ok {
			findings = append(findings, repoConfigFinding("oversized_source_files.excluded_path_prefixes must be a list of strings"))
		} else {
			result.excluded = values
		}
	}
	return result, findings
}
func repoPositiveInteger(value any) (*big.Int, bool) {
	integer, ok := value.(json.Number)
	if !ok || pythonType(value) != "int" {
		return nil, false
	}
	parsed, valid := new(big.Int).SetString(integer.String(), 10)
	return parsed, valid && parsed.Sign() > 0
}

func repoSizeAllowlist(r *repository, name string) ([]string, []Finding) {
	resolved, err := r.resolve(name)
	if err != nil {
		return nil, []Finding{finding("policy-path-unsafe", "oversized_source_files.allowlist_path '"+name+"' is not a safe repo-relative path (absolute, parent-traversal, or resolves outside the repo)", repoPolicyConfig)}
	}
	malformed := func(message string) []Finding { return []Finding{finding("policy-config-malformed", message, name)} }
	if !r.file(resolved) {
		return nil, malformed(name + " is missing or is not a regular file")
	}
	text, err := r.text(resolved)
	if err != nil {
		return nil, malformed(name + " could not be parsed (invalid YAML)")
	}
	value, err := yamlValue([]byte(text), true)
	if err != nil {
		return nil, malformed(name + " could not be parsed (invalid YAML)")
	}
	raw := object(value)
	if raw == nil {
		return nil, malformed(name + " root must be a YAML mapping; got " + pythonType(value))
	}
	if raw.get("files") == nil {
		return []string{}, []Finding{}
	}
	values, ok := stringList(raw.get("files"), false)
	if !ok {
		return nil, malformed(name + " 'files' must be a list of repo-relative path strings")
	}
	values = uniqueStrings(values)
	slices.Sort(values)
	return values, []Finding{}
}
func repoSizeCandidate(name string, policy repoSizePolicy) bool {
	return slices.ContainsFunc(policy.extensions, func(extension string) bool { return strings.HasSuffix(name, extension) }) && slices.ContainsFunc(policy.roots, func(root string) bool { return pathPrefix(name, root) }) && !slices.ContainsFunc(policy.excluded, func(prefix string) bool { return pathPrefix(name, prefix) })
}
func repoByteLineCount(data []byte) int {
	normalized := bytes.ReplaceAll(bytes.ReplaceAll(data, []byte("\r\n"), []byte("\n")), []byte("\r"), []byte("\n"))
	count := bytes.Count(normalized, []byte("\n"))
	if len(normalized) > 0 && normalized[len(normalized)-1] != '\n' {
		count++
	}
	return count
}
