package governance

import (
	"fmt"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"unicode/utf8"

	"golang.org/x/text/cases"
)

const publicResearchRedirect = "../../research.html"
const publicDocsRoot = "docs/public"
const publicSourceLimit = 1_000_000
const publicRedirectLimit = 100_000
const publicIndexLimit = 5_000_000

var publicADRName = regexp.MustCompile(`(?i)^adr-[\p{Nd}]{3,}-`)

type documentationEntry struct {
	name string
	info fs.FileInfo
}

func publicPages() []string {
	return strings.Fields("index.md quickstart.md concepts.md tutorials/first-scenario.md sdl/index.md guides/python.md guides/cli.md backends.md research.md limitations.md contributing.md support.md citation.md")
}
func publicRedirects() [][2]string {
	return [][2]string{
		{"explain/getting-started", "../quickstart.html"},
		{"explain/reference/backend-conformance", "../../backends.html"},
		{"explain/reference/canonical-reference-map", "../../concepts.html"},
		{"explain/reference/documentation-style-guide", "../../contributing.html"},
		{"explain/reference/glossary", "../../concepts.html"},
		{"explain/sdl/index", "../../sdl/index.html"},
		{"explain/sdl/limitations", "../../limitations.html"},
		{"explain/sdl/lineage", publicResearchRedirect},
		{"explain/sdl/related-work-comparison", publicResearchRedirect},
		{"explain/sdl/runtime-architecture", "../../backends.html"},
		{"explain/sdl/scientific-scenario-completeness", publicResearchRedirect},
		{"specs/formal", "../research.html"},
	}
}

func (c *checker) publicDocumentation(r *repository) (Report, error) {
	root, err := r.resolve(publicDocsRoot)
	if err != nil {
		return finish(publicRootFinding()), nil //nolint:nilerr // Unsafe or missing source roots are policy findings.
	}
	info, err := r.root.Stat(root)
	if err != nil || !info.IsDir() {
		return finish(publicRootFinding()), nil //nolint:nilerr // Unsafe or missing source roots are policy findings.
	}
	entries, err := documentationEntries(r, root)
	if err != nil {
		return Report{}, err
	}
	sources := documentationSources(entries)
	findings := publicSourceFindings(r, root, entries, sources)
	findings = append(findings, publicBoundaryFindings(r, root, entries, sources)...)
	if len(findings) == 0 && c.request.OutputRoot != "" {
		output, outputErr := publicOutputPath(r, c.request.OutputRoot)
		if outputErr != nil {
			return finish([]Finding{finding("public-docs-output-root", "generated documentation output must stay inside the repository", c.request.OutputRoot)}), nil //nolint:nilerr // Output containment is an evaluated policy rule.
		}
		outputFindings, outputErr := publicOutputFindings(r, root, output, c.request.OutputRoot, sources)
		if outputErr != nil {
			return Report{}, outputErr
		}
		findings = append(findings, outputFindings...)
		assets, assetErr := publicAssetFindings(r, root, output, entries)
		if assetErr != nil {
			return Report{}, assetErr
		}
		findings = append(findings, assets...)
	}
	return finish(findings), nil
}

func publicRootFinding() []Finding {
	return []Finding{finding("public-docs-root", "the curated public documentation root is missing or unsafe", publicDocsRoot)}
}

func documentationEntries(r *repository, root string) ([]documentationEntry, error) {
	anchor, err := r.resolve(root)
	if err != nil {
		return nil, err
	}
	return walkDocumentationEntries(r.root.FS(), anchor, root)
}

func walkDocumentationEntries(tree fs.FS, anchor, root string) ([]documentationEntry, error) {
	result := []documentationEntry{}
	walkErr := fs.WalkDir(tree, anchor, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return nil //nolint:nilerr // Path.rglob and os.walk suppress unreadable subtrees.
		}
		if secretPath(name) {
			return errUnsafePath
		}
		if name == anchor {
			return nil
		}
		if info, err := entry.Info(); err == nil {
			result = append(result, documentationEntry{path.Join(root, strings.TrimPrefix(strings.TrimPrefix(name, anchor), "/")), info})
		}
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}
	slices.SortFunc(result, func(a, b documentationEntry) int { return strings.Compare(a.name, b.name) })
	return result, nil
}
func documentationSourceSuffix(name string) bool {
	return slices.Contains([]string{".md", ".rst"}, cases.Fold().String(path.Ext(strings.TrimLeft(path.Base(name), "."))))
}
func documentationSources(entries []documentationEntry) []string {
	names := []string{}
	for _, entry := range entries {
		if entry.info.Mode().IsRegular() && documentationSourceSuffix(entry.name) {
			names = append(names, entry.name)
		}
	}
	return names
}

func publicSourceFindings(r *repository, root string, entries []documentationEntry, sources []string) []Finding {
	findings := []Finding{}
	for _, page := range publicPages() {
		name := path.Join(root, page)
		info, err := r.root.Lstat(name)
		if err != nil || !info.Mode().IsRegular() {
			findings = append(findings, finding("public-docs-information-architecture", "required public page is missing", path.Join(publicDocsRoot, page)))
		}
	}
	if err := publicRedirectMap(r, path.Join(root, "redirects.json")); err != nil {
		findings = append(findings, finding("public-docs-redirect-map", err.Error(), path.Join(root, "redirects.json")))
	}
	for _, entry := range entries {
		if entry.info.Mode()&os.ModeSymlink != 0 {
			findings = append(findings, finding("public-docs-symlink", "public documentation must not contain symlinks", entry.name))
		}
	}
	for _, name := range sources {
		findings = append(findings, inspectPublicSource(r, root, name)...)
	}
	sortFindings(findings)
	return findings
}

func publicRedirectMap(r *repository, name string) error {
	info, err := r.root.Lstat(name)
	if err != nil || !info.Mode().IsRegular() || info.Size() > publicRedirectLimit {
		return policyInputError("redirect map is missing, unsafe, or exceeds the inspection limit")
	}
	text, err := r.text(name)
	if err != nil {
		return err
	}
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return err
	}
	actual := object(value)
	if actual == nil {
		return policyInputError("redirect map must contain string source and target pairs")
	}
	for _, key := range actual.keys {
		if _, ok := actual.get(key).(string); !ok {
			return policyInputError("redirect map must contain string source and target pairs")
		}
	}
	expected := newMapping()
	for _, redirect := range publicRedirects() {
		expected.set(redirect[0], redirect[1])
	}
	if !publicationEqual(actual, expected) {
		return policyInputError("redirect map must preserve the complete established public-route contract")
	}
	return nil
}

func inspectPublicSource(r *repository, root, name string) []Finding {
	info, err := r.root.Stat(name)
	if err != nil {
		return []Finding{finding("public-docs-source-readable", "public source must be readable UTF-8 text", name)}
	}
	if info.Size() > publicSourceLimit {
		return []Finding{finding("public-docs-source-size", fmt.Sprintf("public source exceeds the %d-byte inspection limit", publicSourceLimit), name)}
	}
	text, err := r.text(name)
	if err != nil {
		return []Finding{finding("public-docs-source-readable", "public source must be readable UTF-8 text", name)}
	}
	for _, target := range directiveTargets(text) {
		if !publicTargetContained(r, root, name, target, false) {
			return []Finding{finding("public-docs-source-escape", "include, literalinclude, download, :file:, :url: and :diff: targets must stay inside docs/public", name)}
		}
	}
	return nil
}

func publicBoundaryFindings(r *repository, root string, entries []documentationEntry, sources []string) []Finding {
	findings := []Finding{}
	for _, entry := range entries {
		relative := strings.TrimPrefix(entry.name, root+"/")
		if publicInternalRecord(relative) && r.file(entry.name) {
			findings = append(findings, finding("public-docs-internal-record", "decision records and development notes must stay outside docs/public", entry.name))
		}
	}
	for _, source := range sources {
		if strings.ToLower(path.Ext(source)) != ".md" {
			continue
		}
		data, err := r.readLimit(source, publicSourceLimit)
		if err != nil || !utf8.Valid(data) {
			continue
		}
		for _, target := range markdownLinkTargets(string(data)) {
			if !publicTargetContained(r, root, source, target, true) {
				findings = append(findings, finding("public-docs-link-escape", "link target "+pythonRepr(target)+" resolves outside docs/public; link repository files by absolute URL", source))
			}
		}
	}
	return findings
}

func publicInternalRecord(relative string) bool {
	parts := strings.Split(relative, "/")
	for _, part := range parts[:len(parts)-1] {
		if slices.Contains([]string{"adrs", "decisions", "development"}, part) {
			return true
		}
	}
	return documentationSourceSuffix(relative) && publicADRName.MatchString(path.Base(relative))
}

func publicTargetContained(r *repository, root, source, target string, markdown bool) bool {
	if strings.HasPrefix(strings.ToLower(target), "file:") {
		return false
	}
	candidate, _, _ := strings.Cut(target, "#")
	if candidate == "" || strings.Contains(target, "://") || strings.HasPrefix(target, "mailto:") {
		return true
	}
	base := path.Dir(source)
	if strings.HasPrefix(candidate, "/") {
		if !markdown || strings.HasPrefix(candidate, "//") {
			return false
		}
		base = root
		candidate = strings.TrimPrefix(candidate, "/")
	}
	resolved, err := documentPath(r.absolute, base+"/"+candidate)
	return err == nil && containedDocumentPath(filepath.Join(r.absolute, root), resolved)
}
