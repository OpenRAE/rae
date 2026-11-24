package governance

import (
	"net/url"
	"path"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
)

var publicSearchWrapper = regexp.MustCompile(`(?s)^[` + fixedWhitespaceClass + `]*Search\.setIndex\((.*)\)[` + fixedWhitespaceClass + `]*;?[` + fixedWhitespaceClass + `]*\z`)

func publicOutputPath(r *repository, selection string) (string, error) {
	absolute, err := documentPath(r.absolute, selection)
	if err != nil {
		return "", err
	}
	if !containedDocumentPath(r.absolute, absolute) {
		return "", errUnsafePath
	}
	return filepath.Rel(r.absolute, absolute)
}

func publicOutputFindings(r *repository, root, output, display string, sources []string) ([]Finding, error) {
	expected, docnames := publicSourceRoutes(root, sources)
	allowed := append(slices.Clone(expected), "genindex.html", "py-modindex.html", "search.html")
	for _, redirect := range publicRedirects() {
		allowed = append(allowed, redirect[0]+".html")
	}
	findings := []Finding{}
	entries, err := documentationEntries(r, output)
	if err != nil {
		return nil, err
	}
	for _, entry := range entries {
		route := strings.TrimPrefix(entry.name, output+"/")
		if path.Ext(route) == ".html" && !slices.Contains(strings.Split(route, "/"), "_static") && !slices.Contains(allowed, route) {
			findings = append(findings, finding("public-docs-output-route", "generated HTML route has no source beneath docs/public", route))
		}
	}
	for _, redirect := range publicRedirects() {
		route := redirect[0] + ".html"
		if redirectErr := publicRedirectOutput(r, path.Join(output, route), redirect[1]); redirectErr != nil {
			findings = append(findings, finding("public-docs-redirect-output", redirectErr.Error(), route))
		}
	}
	findings = append(findings, publicSearchFindings(r, output, display, docnames)...)
	findings = append(findings, publicSitemapFindings(r, output, display, expected, allowed)...)

	return findings, nil
}

func publicSearchFindings(r *repository, output, display string, docnames []string) []Finding {
	findings := []Finding{}
	search, err := publicSearchDocnames(r, path.Join(output, "searchindex.js"))
	if err != nil {
		findings = append(findings, finding("public-docs-search-index", err.Error(), publicOutputDisplay(display, "searchindex.js")))
	} else {
		for _, name := range search {
			if !slices.Contains(docnames, name) {
				findings = append(findings, finding("public-docs-search-route", "search document has no source beneath docs/public", name))
			}
		}
	}
	return findings
}
func publicSitemapFindings(r *repository, output, display string, expected, allowed []string) []Finding {
	findings := []Finding{}

	sitemap := path.Join(output, "sitemap.xml")
	if r.file(sitemap) {
		routes, err := publicSitemapRoutes(r, sitemap)
		if err != nil {
			findings = append(findings, finding("public-docs-sitemap", "invalid sitemap: "+err.Error(), publicOutputDisplay(display, "sitemap.xml")))
		} else {
			for _, route := range publicSitemapUnexpected(routes, expected, allowed) {
				findings = append(findings, finding("public-docs-sitemap-route", "sitemap route has no source beneath docs/public", route))
			}
		}
	}
	return findings
}

func publicOutputDisplay(root, leaf string) string {
	display := prefixPath(root)
	if strings.HasPrefix(root, "/") {
		display = "/" + display
	}
	if strings.HasPrefix(root, "//") && !strings.HasPrefix(root, "///") {
		display = "/" + display
	}
	if display == "." {
		return leaf
	}
	return strings.TrimSuffix(display, "/") + "/" + leaf
}

func publicSourceRoutes(root string, sources []string) ([]string, []string) {
	routes, docnames := []string{}, []string{}
	for _, source := range sources {
		relative := strings.TrimPrefix(source, root+"/")
		name := strings.TrimSuffix(relative, path.Ext(relative))
		docnames = append(docnames, name)
		routes = append(routes, name+".html")
	}
	return uniqueStrings(routes), uniqueStrings(docnames)
}

func publicBoundedOutputText(r *repository, name string, limit int64, message string) (string, error) {
	if !r.file(name) {
		return "", policyInputError(message)
	}
	resolved, err := r.resolve(name)
	if err != nil {
		return "", err
	}
	info, err := r.root.Stat(resolved)
	if err != nil {
		return "", err
	}
	if info.Size() > limit {
		return "", policyInputError(message)
	}
	return r.text(name)
}
func publicRedirectOutput(r *repository, name, target string) error {
	text, err := publicBoundedOutputText(r, name, publicRedirectLimit, "redirect page is missing or exceeds the inspection limit")
	if err != nil {
		return err
	}
	normalized := strings.Join(strings.FieldsFunc(strings.ToLower(text), pythonWhitespace), " ")
	if !strings.Contains(normalized, `http-equiv="refresh"`) || !strings.Contains(normalized, "url="+strings.ToLower(target)) {
		return policyInputError("redirect page does not point to its curated public target")
	}
	return nil
}
func publicSearchDocnames(r *repository, name string) ([]string, error) {
	text, err := publicBoundedOutputText(r, name, publicIndexLimit, "searchindex.js is missing or exceeds the inspection limit")
	if err != nil {
		return nil, err
	}
	match := publicSearchWrapper.FindStringSubmatch(text)
	if match == nil {
		return nil, policyInputError("searchindex.js does not contain a recognized Sphinx index")
	}
	value, err := decodeJSON([]byte(match[1]), 0, false)
	if err != nil {
		return nil, err
	}
	if object(value) == nil {
		return nil, policyInputError("searchindex.js payload must be an object")
	}
	names, ok := stringList(object(value).get("docnames"), false)
	if !ok {
		return nil, policyInputError("searchindex.js has no string docnames inventory")
	}
	names = uniqueStrings(names)
	slices.Sort(names)
	return names, nil
}

func publicSitemapRoutes(r *repository, name string) ([]string, error) {
	data, err := r.read(name)
	if err != nil {
		return nil, err
	}
	root, err := parsePolicyXML(data)
	if err != nil {
		return nil, err
	}
	routes := []string{}
	for _, location := range root.elements("*", "loc", true) {
		text := location.text.String()
		if text == "" {
			continue
		}
		parsed, err := url.Parse(text)
		if err != nil {
			return nil, policyInputError("sitemap location is not a URL that urllib can parse")
		}
		route := strings.Trim(parsed.EscapedPath(), "/")
		if route == "" {
			route = "index.html"
		}
		routes = append(routes, route)
	}
	return uniqueStrings(routes), nil
}

func publicSitemapUnexpected(routes, expected, allowed []string) []string {
	type routeMapping struct{ route, matched, prefix string }
	mappings := []routeMapping{}
	unexpected := []string{}
	prefixes := map[string]int{}
	expectedPrefixes := map[string]bool{}
	represented := map[string]bool{}
	for _, route := range routes {
		matched := longestPublicSitemapMatch(route, allowed)
		if matched == "" {
			unexpected = append(unexpected, route)
			continue
		}
		prefix := strings.TrimSuffix(route, matched)
		mappings = append(mappings, routeMapping{route, matched, prefix})
		prefixes[prefix]++
		if slices.Contains(expected, matched) {
			expectedPrefixes[prefix] = true
			represented[matched] = true
		}
	}
	common := publicSitemapCommonPrefix(expectedPrefixes, prefixes)
	if len(expectedPrefixes) > 1 {
		for _, item := range mappings {
			if slices.Contains(expected, item.matched) && item.prefix != common {
				unexpected = append(unexpected, item.route)
			}
		}
	}
	for _, route := range expected {
		if !represented[route] {
			unexpected = append(unexpected, "missing public source routes")
			break
		}
	}
	unexpected = uniqueStrings(unexpected)
	slices.Sort(unexpected)
	return unexpected
}

func longestPublicSitemapMatch(route string, allowed []string) string {
	matched := ""
	for _, candidate := range allowed {
		if (route == candidate || strings.HasSuffix(route, "/"+candidate)) && len(candidate) > len(matched) {
			matched = candidate
		}
	}
	return matched
}
func publicSitemapCommonPrefix(expected map[string]bool, counts map[string]int) string {
	common := ""
	for prefix := range expected {
		if counts[prefix] > counts[common] || counts[prefix] == counts[common] && prefix < common {
			common = prefix
		}
	}
	return common
}
