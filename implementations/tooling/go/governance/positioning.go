package governance

import (
	"context"
	"strings"

	"golang.org/x/text/cases"
)

const positioningLimit = 512_000
const positioningSurfaceRule = "project-positioning-surface"
const positioningFramingRule = "project-positioning-framing"
const positioningMetadataRule = "project-positioning-metadata"

func positioningPrimary() []string { return []string{"README.md", "docs/public/index.md"} }
func positioningSupporting() []string {
	return []string{"docs/public/quickstart.md", "docs/public/concepts.md", "docs/public/sdl/index.md", "docs/public/backends.md", "docs/public/research.md", "examples/README.md"}
}

func (c *checker) projectPositioning(ctx context.Context, r *repository) (Report, error) {
	findings := []Finding{}
	surfaces := map[string]string{}
	for _, group := range [][]string{positioningPrimary(), positioningSupporting()} {
		for _, name := range group {
			surfaces[name] = positioningText(r, name, &findings)
		}
	}
	positioningFraming(surfaces, &findings)
	positioningMetadata(ctx, r, &findings)
	if err := ctx.Err(); err != nil {
		return Report{}, err
	}
	entries, err := loadExceptions(r)
	if err != nil {
		return Report{}, err
	}
	findings, err = applyExceptions(findings, entries, "", c.request.Today)
	return finish(findings), err
}

func positioningText(r *repository, name string, findings *[]Finding) string {
	fail := func(message string) string {
		*findings = append(*findings, finding(positioningSurfaceRule, message, name))
		return ""
	}
	if !r.file(name) {
		return fail("required positioning surface is missing")
	}
	const unreadable = "positioning surface is not readable UTF-8 text"
	resolved, err := r.resolve(name)
	if err != nil {
		return fail(unreadable)
	}
	info, err := r.root.Stat(resolved)
	if err != nil {
		return fail(unreadable)
	}
	if info.Size() > positioningLimit {
		return fail("positioning surface exceeds the 512000-byte inspection limit")
	}
	text, err := r.text(name)
	if err != nil {
		return fail(unreadable)
	}
	return text
}

func positioningTerms(text string, terms ...string) bool {
	normalize := func(value string) string {
		return strings.Join(strings.FieldsFunc(cases.Fold().String(value), func(r rune) bool { return pythonWhitespace(r) || r == '-' }), " ")
	}
	text = normalize(text)
	for _, term := range terms {
		if !strings.Contains(text, normalize(term)) {
			return false
		}
	}
	return true
}

func positioningFraming(surfaces map[string]string, findings *[]Finding) {
	for _, name := range positioningPrimary() {
		if !positioningTerms(surfaces[name], "reproducible agentic environments system", "agentic environment") {
			*findings = append(*findings, finding(positioningFramingRule, "primary entrypoint must introduce RAES and agentic environments", name))
		}
	}
	for _, name := range positioningSupporting() {
		if !positioningTerms(surfaces[name], "RAES") {
			*findings = append(*findings, finding(positioningFramingRule, "supporting entrypoint must connect its subject to RAES", name))
		}
	}
	readme := surfaces["README.md"]
	if !positioningTerms(readme, "cyber", "ai security", "ai safety", "testing", "research", "evaluation") || !positioningTerms(readme, "additional domains") && !positioningTerms(readme, "other domains") {
		*findings = append(*findings, finding("project-positioning-domains", "README must present the named application areas as non-exhaustive", "README.md"))
	}
	if !positioningTerms(surfaces["docs/public/concepts.md"], "authored scenario", "realized environment", "bounded reproduction", "does not", "exact replay") {
		*findings = append(*findings, finding("project-positioning-claim-boundary", "concept guidance must retain the bounded reproduction and nonclaim boundary", "docs/public/concepts.md"))
	}
}

func positioningMetadata(ctx context.Context, r *repository, findings *[]Finding) {
	const projectPath = "implementations/python/pyproject.toml"
	if source := positioningText(r, projectPath, findings); source != "" {
		description, valid := positioningTOMLDescription([]byte(source))
		if !valid || !strings.Contains(cases.Fold().String(description), "reproducible agentic environments") {
			*findings = append(*findings, finding(positioningMetadataRule, "package description must identify reproducible agentic environments", projectPath))
		}
	}
	const configPath = "docs/public/conf.py"
	source := positioningText(r, configPath, findings)
	metadata := pythonLiteralAssignments(ctx, source, "project", "html_title")
	if metadata["project"] != "Reproducible Agentic Environments System" || metadata["html_title"] != "RAES Documentation" {
		*findings = append(*findings, finding(positioningMetadataRule, "Sphinx metadata must identify the RAES system and documentation surface", configPath))
	}
	const catalogPath = "examples/library/catalog.yaml"
	source = positioningText(r, catalogPath, findings)
	value, err := yamlValue([]byte(source), false)
	catalog, _ := value.(*mapping)
	description, _ := catalog.get("description").(string)
	if err != nil || !positioningTerms(description, "domain-neutral", "agentic environment") {
		*findings = append(*findings, finding(positioningMetadataRule, "example catalog description must identify its domain-neutral agentic-environment role", catalogPath))
	}
	for _, assignment := range [][2]string{{"implementations/python/packages/raes_mcp/server.py", "_INSTRUCTIONS"}, {"implementations/python/packages/raes_mcp/tools/reference.py", "_OVERVIEW_TEXT"}} {
		source = positioningText(r, assignment[0], findings)
		value := pythonLiteralAssignments(ctx, source, assignment[1])[assignment[1]]
		if !positioningTerms(value, "agentic environment", "RAES SDL", "authored scenario") {
			*findings = append(*findings, finding(positioningMetadataRule, "MCP positioning must distinguish RAES agentic environments from authored RAES SDL scenarios", assignment[0]))
		}
	}
}
