package governance

import "strconv"

const moduleRootPrefix = ".root '"

func repoModuleConfig(r *repository, value any) ([]repoModule, []Finding) {
	fail := func(message string) ([]repoModule, []Finding) { return nil, []Finding{repoConfigFinding(message)} }
	if value == nil {
		return fail("module_boundaries block is required (ADR-036 / MOD-001) but is absent")
	}
	raw := object(value)
	if raw == nil {
		return fail("module_boundaries must be a mapping; got " + pythonType(value))
	}
	adr, _ := raw.get("adr").(string)
	if adr == "" {
		return fail("module_boundaries.adr must be a non-empty string; got " + pythonRepr(raw.get("adr")))
	}
	entries, ok := raw.get("modules").([]any)
	if !ok || len(entries) == 0 {
		return fail("module_boundaries.modules must be a non-empty list")
	}
	roots, ok := stringList(raw.get("package_coverage_roots"), false)
	if !ok || len(roots) == 0 {
		return fail("module_boundaries.package_coverage_roots must be a non-empty list of strings")
	}
	findings := []Finding{}
	rules := []repoModule{}
	ids, seen := map[string]bool{}, map[string]bool{}
	for i, value := range entries {
		prefix := "module_boundaries.modules[" + strconv.Itoa(i) + "]"
		row := object(value)
		if row == nil {
			findings = append(findings, repoConfigFinding(prefix+" must be a mapping"))
			continue
		}
		rule, problems := repoModuleFields(r, row, prefix, ids, seen)
		findings = append(findings, problems...)
		if len(problems) > 0 {
			continue
		}
		ids[rule.id] = true
		seen[rule.root] = true
		rules = append(rules, rule)
	}
	if len(findings) > 0 {
		return rules, findings
	}
	return rules, repoPackageCoverage(r, roots, seen)
}

func repoModuleFields(r *repository, row *mapping, prefix string, ids, roots map[string]bool) (repoModule, []Finding) {
	result := repoModule{public: map[string][]string{}}
	findings := []Finding{}
	fail := func(message string) { findings = append(findings, repoConfigFinding(prefix+message)) }
	result.id, _ = row.get("id").(string)
	result.root, _ = row.get("root").(string)
	if result.id == "" {
		fail(".id must be a non-empty string")
	} else if ids[result.id] {
		fail(".id '" + result.id + "' is duplicated")
	}
	switch {
	case result.root == "":
		fail(".root must be a non-empty string")
	case roots[result.root]:
		fail(moduleRootPrefix + result.root + "' is duplicated")
	case !r.safe(result.root):
		fail(moduleRootPrefix + result.root + "' must be a safe repo-relative path")
	case !repoDirectory(r, result.root):
		fail(moduleRootPrefix + result.root + "' must resolve to an existing directory")
	}
	for _, field := range []struct {
		name   string
		target *[]string
	}{{"allowed_top_level_imports", &result.allowed}, {"forbidden_import_prefixes", &result.forbidden}} {
		*field.target = []string{}
		if row.has(field.name) {
			values, ok := stringList(row.get(field.name), false)
			if !ok {
				fail("." + field.name + " must be a list of strings")
			} else {
				*field.target = values
			}
		}
	}
	public, problem := repoPublicImports(row.get("public_import_prefixes"))
	result.public = public
	if problem != "" {
		fail(problem)
	}
	return result, findings
}
func repoPublicImports(value any) (map[string][]string, string) {
	result := map[string][]string{}
	if value == nil {
		return result, ""
	}
	mapping := object(value)
	if mapping == nil {
		return result, ".public_import_prefixes must be a mapping"
	}
	for _, key := range mapping.keys {
		name, textual := key.(string)
		prefixes, ok := stringList(mapping.get(key), false)
		if !textual || !ok || len(prefixes) == 0 {
			return result, ".public_import_prefixes values must be non-empty lists of strings"
		}
		result[name] = prefixes
	}
	return result, ""
}
