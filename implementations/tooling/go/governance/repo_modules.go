package governance

import (
	"context"
	"io/fs"
	"path"
	"slices"
	"strings"
)

type repoModule struct {
	id, root           string
	allowed, forbidden []string
	public             map[string][]string
}

func repoModules(ctx context.Context, r *repository, policy *mapping, changed []string, checkSet string) ([]Finding, error) {
	rules, findings := repoModuleConfig(r, policy.get("module_boundaries"))
	if len(findings) > 0 || len(rules) == 0 {
		return findings, nil
	}
	candidates, err := repoModulePaths(r, rules, changed, checkSet)
	if err != nil {
		return nil, err
	}
	known := map[string]bool{}
	for _, rule := range rules {
		known[rule.id] = true
	}
	for _, rule := range rules {
		problems, scanErr := repoModuleFiles(ctx, r, rule, known, candidates)
		if scanErr != nil {
			return nil, scanErr
		}
		findings = append(findings, problems...)
	}
	return findings, nil
}

func repoModuleFiles(ctx context.Context, r *repository, rule repoModule, known map[string]bool, candidates []string) ([]Finding, error) {
	findings := []Finding{}
	for _, name := range candidates {
		if !strings.HasSuffix(name, ".py") || !pathPrefix(name, rule.root) || !r.file(name) {
			continue
		}
		facts, err := repoPython(ctx, r, name)
		if err != nil {
			return nil, err
		}
		findings = append(findings, repoModuleImports(rule, known, facts.imports, name)...)
		if rule.id == "raes_backend_protocols" {
			findings = append(findings, repoProtocolFindings(facts.untyped, name)...)
		}
	}
	return findings, nil
}

func repoModuleImports(rule repoModule, known map[string]bool, imports []repoPythonImport, name string) []Finding {
	findings := []Finding{}
	for _, entry := range imports {
		for _, imported := range entry.absoluteNames() {
			if problem := repoModuleImport(rule, known, imported, name); problem != nil {
				findings = append(findings, *problem)
			}
		}
	}
	return findings
}
func repoProtocolFindings(methods []string, name string) []Finding {
	result := []Finding{}
	for _, method := range methods {
		result = append(result, finding("backend-protocol-untyped-contract", method+" uses Any in its public protocol signature; backend protocols must use neutral contract DTOs from raes_contracts", name))
	}
	return result
}
func (entry repoPythonImport) absoluteNames() []string {
	if !entry.from {
		return entry.names
	}
	if entry.relative || entry.module == "" {
		return nil
	}
	names := make([]string, len(entry.names))
	for i, item := range entry.names {
		names[i] = entry.module
		if item != "*" {
			names[i] += "." + item
		}
	}
	return names
}

func repoModulePaths(r *repository, rules []repoModule, changed []string, checkSet string) ([]string, error) {
	if checkSet != repoFullCheck {
		return changed, nil
	}
	result := []string{}
	seen := map[string]bool{}
	for _, rule := range rules {
		paths, err := repoModuleRootPaths(r, rule.root)
		if err != nil {
			return nil, err
		}
		for _, name := range paths {
			if !seen[name] {
				seen[name] = true
				result = append(result, name)
			}
		}
	}
	return result, nil
}
func repoModuleRootPaths(r *repository, root string) ([]string, error) {
	entries, err := documentationEntries(r, root)
	if err != nil {
		return nil, err
	}
	paths := []string{}
	for _, entry := range entries {
		if !strings.HasSuffix(entry.name, ".py") || entry.info.IsDir() {
			continue
		}
		if _, resolveErr := r.resolve(entry.name); resolveErr != nil {
			return nil, resolveErr
		}
		if r.file(entry.name) {
			paths = append(paths, entry.name)
		}
	}
	slices.Sort(paths)
	return paths, nil
}

func repoModuleImport(rule repoModule, known map[string]bool, imported, name string) *Finding {
	top, _, _ := strings.Cut(imported, ".")
	if top == rule.id || !known[top] {
		return nil
	}
	problem := Finding{}
	switch {
	case repoImportPrefix(imported, rule.forbidden):
		problem = finding("module-boundary-import", rule.id+" must not import "+pythonRepr(imported)+"; module-boundary rules are defined by module_boundaries", name)
	case slices.ContainsFunc(strings.Split(imported, ".")[1:], func(part string) bool { return strings.HasPrefix(part, "_") }):
		problem = finding("module-boundary-private-import", rule.id+" must not import private/internal module path "+pythonRepr(imported), name)
	case len(rule.public[top]) > 0 && !repoImportPrefix(imported, rule.public[top]):
		prefixes := slices.Clone(rule.public[top])
		slices.Sort(prefixes)
		values := make([]any, len(prefixes))
		for i, value := range prefixes {
			values[i] = value
		}
		problem = finding("module-boundary-public-api", rule.id+" may import "+top+" only through public prefixes "+pythonRepr(values), name)
	case !slices.Contains(rule.allowed, top):
		problem = finding("module-boundary-import", rule.id+" may not import "+top+"; add an ADR-backed module-boundary allowance first", name)
	default:
		return nil
	}
	return &problem
}
func repoImportPrefix(imported string, prefixes []string) bool {
	return slices.ContainsFunc(prefixes, func(prefix string) bool { return imported == prefix || strings.HasPrefix(imported, prefix+".") })
}

func repoDirectory(r *repository, name string) bool {
	resolved, err := r.resolve(name)
	if err != nil {
		return false
	}
	info, err := r.root.Stat(resolved)
	return err == nil && info.IsDir()
}

func repoPackageCoverage(r *repository, roots []string, seen map[string]bool) []Finding {
	findings := []Finding{}
	for _, root := range roots {
		findings = append(findings, repoPackageRootCoverage(r, root, seen)...)
	}
	return findings
}
func repoPackageRootCoverage(r *repository, root string, seen map[string]bool) []Finding {
	prefix := "module_boundaries.package_coverage_roots entry '" + root + "' "
	fail := func(message string) []Finding { return []Finding{repoConfigFinding(prefix + message)} }
	resolved, err := r.resolve(root)
	if err != nil {
		return fail("must be a safe repo-relative path")
	}
	if !repoDirectory(r, resolved) {
		return fail("must resolve to an existing directory")
	}
	entries, err := fs.ReadDir(r.root.FS(), resolved)
	if err != nil {
		return fail("could not be read")
	}
	findings := []Finding{}
	for _, entry := range entries {
		name := path.Join(resolved, entry.Name())
		if !r.safe(name) {
			findings = append(findings, fail("contains an unsafe repository path")...)
			continue
		}
		if repoDirectory(r, name) && r.file(name+"/__init__.py") && !seen[name] {
			findings = append(findings, repoConfigFinding("package root '"+name+"' is missing from module_boundaries.modules; every first-party package must have an ADR-backed module boundary"))
		}
	}
	return findings
}
