package governance

import (
	"path/filepath"
	"slices"
	"strings"
)

func (c *checker) documentationReads(r *repository) (Report, error) {
	observations := c.request.Documentation
	if observations == nil {
		return Report{}, policyInputError("documentation checks require actual builder read records")
	}
	root, err := documentPath(r.absolute, observations.SourceRoot)
	if err != nil {
		return Report{}, err
	}

	outside := map[string]map[string]bool{}
	for _, read := range observations.Reads {
		name, readErr := documentPath(root, read.File)
		if readErr != nil {
			return Report{}, readErr
		}
		if containedDocumentPath(root, name) {
			continue
		}
		if outside[read.Page] == nil {
			outside[read.Page] = map[string]bool{}
		}
		outside[read.Page][name] = true
	}
	modules := map[string]bool{}
	if documentModuleExemptionNeeded(outside) {
		modules, err = documentedModules(r, observations)
		if err != nil {
			return Report{}, err
		}
	}
	return finish(documentReadFindings(outside, modules)), nil
}

func documentReadFindings(outside map[string]map[string]bool, modules map[string]bool) []Finding {
	pages := []string{}
	for page := range outside {
		pages = append(pages, page)
	}
	slices.Sort(pages)
	findings := []Finding{}
	for _, page := range pages {
		applyDocumentModuleExemption(outside[page], modules)
		names := []string{}
		for name := range outside[page] {
			names = append(names, name)
		}
		slices.Sort(names)
		for _, name := range names {
			findings = append(findings, finding("public-docs-read-escape", "page reads "+name+", which is outside the documentation source directory", page))
		}
	}
	return findings
}

func applyDocumentModuleExemption(outside, modules map[string]bool) {
	for name := range outside {
		if documentModuleSuffix(name) {
			for module := range modules {
				delete(outside, module)
			}
			return
		}
	}
}

func documentPath(base, name string) (string, error) {
	if !filepath.IsAbs(name) {
		name = base + string(filepath.Separator) + name
	}
	absolute, err := absoluteReferencePath(name)
	if err != nil {
		return "", err
	}
	return repositoryDirectory(absolute)
}

func containedDocumentPath(root, name string) bool {
	return name == root || strings.HasPrefix(name, strings.TrimRight(root, string(filepath.Separator))+string(filepath.Separator))
}
func documentModuleSuffix(name string) bool {
	return slices.Contains([]string{".py", ".pyc", ".so"}, filepath.Ext(strings.TrimLeft(filepath.Base(name), ".")))
}

func documentedModules(r *repository, observations *Documentation) (map[string]bool, error) {
	roots := []string{}
	for _, root := range observations.ModuleRoots {
		canonical, err := documentPath(r.absolute, root)
		if err != nil {
			return nil, err
		}
		roots = append(roots, canonical)
	}
	modules := map[string]bool{}
	for _, module := range observations.ImportedModules {
		name, err := documentPath(r.absolute, module)
		if err != nil {
			return nil, err
		}
		for _, root := range roots {
			if containedDocumentPath(root, name) {
				modules[name] = true
				break
			}
		}
	}
	return modules, nil
}

func documentModuleExemptionNeeded(outside map[string]map[string]bool) bool {
	for _, files := range outside {
		for name := range files {
			if documentModuleSuffix(name) {
				return true
			}
		}
	}
	return false
}
