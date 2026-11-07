package governance

import (
	"fmt"
	"slices"
	"strings"
	"unicode/utf8"
)

func boundedCoverageString(value any, label string, minimum, maximum int) string {
	text, ok := value.(string)
	if !ok {
		return label + " must be a string"
	}
	count := utf8.RuneCountInString(strings.TrimFunc(text, pythonWhitespace))
	if count < minimum || count > maximum {
		return fmt.Sprintf("%s must be between %d and %d characters", label, minimum, maximum)
	}
	return ""
}

func coverageUnknownKeys(m *mapping, allowed []string, label string) string {
	unknown := []string{}
	for _, key := range sortedMappingKeys(m) {
		if !slices.Contains(allowed, key) {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) > 0 {
		return label + " has unsupported keys: " + strings.Join(unknown, ", ")
	}
	return ""
}

type coverageSourceIdentity struct {
	path    string
	pointer any
}
type coveragePointerJSON string

func coverageDeclaration(r *repository, raw any, id, schema string) (bool, []Finding, error) {
	declaration, ok := raw.(*mapping)
	if !ok {
		return false, []Finding{finding(coverageDeclarationRule, "coverage must be a JSON object", schema)}, nil
	}
	reasons := []string{}
	for _, reason := range []string{coverageUnknownKeys(declaration, []string{"rationale", "sources"}, "coverage"), boundedCoverageString(declaration.get("rationale"), "coverage rationale", 20, 500)} {
		if reason != "" {
			reasons = append(reasons, reason)
		}
	}
	sources, ok := declaration.get("sources").([]any)
	if !ok || len(sources) == 0 {
		reasons = append(reasons, "coverage sources must be a non-empty array")
		sources = nil
	} else if len(sources) > 8 {
		reasons = append(reasons, "coverage sources must name at most 8 artifacts")
		sources = nil
	}
	seen := map[coverageSourceIdentity]bool{}
	qualified := false
	for _, source := range sources {
		reason, err := coverageSource(r, source, seen, id, schema)
		if err != nil {
			return false, nil, err
		}
		if reason == "" {
			qualified = true
		} else {
			reasons = append(reasons, reason)
		}
	}
	failures := make([]Finding, len(reasons))
	for i, reason := range reasons {
		failures[i] = finding(coverageDeclarationRule, reason, schema)
	}
	return qualified && len(reasons) == 0, failures, nil
}

func coverageSource(r *repository, raw any, seen map[coverageSourceIdentity]bool, id, schema string) (string, error) {
	source, ok := raw.(*mapping)
	if !ok {
		return "each coverage source must be a JSON object", nil
	}
	if reason := coverageUnknownKeys(source, []string{"kind", "path", "pointer", "schema_pointer", "supports"}, "coverage source"); reason != "" {
		return reason, nil
	}
	if reason := boundedCoverageString(source.get("supports"), "coverage source supports", 10, 200); reason != "" {
		return reason, nil
	}
	if reason := coverageSourcePath(r, source.get("path")); reason != "" {
		return reason, nil
	}
	name, _ := source.get("path").(string)
	node := source.get("pointer")
	if !yamlHashable(node) {
		node = coveragePointerJSON(pythonRepr(coverageIdentityValue(node)))
	} else {
		node = yamlKey(node)
	}
	identity := coverageSourceIdentity{name, node}
	if seen[identity] {
		return "coverage sources must be unique: " + name, nil
	}
	seen[identity] = true
	switch source.get("kind") {
	case "fixture":
		return coverageFixture(r, name, id, schema)
	case "embedded":
		return coverageEmbedded(r, name, schema, source.get("pointer"), source.get("schema_pointer"))
	default:
		return "coverage source kind must be one of ['embedded', 'fixture']: " + name, nil
	}
}

func coverageSourcePath(r *repository, value any) string {
	name, ok := value.(string)
	if !ok || name == "" {
		return "source path must be a non-empty string"
	}
	if prefixPath(name) != name || strings.HasPrefix(name, "/") {
		return "source path must be a normalized repo-relative path: " + name
	}
	if !r.safe(name) {
		return "source path escapes the repository: " + name
	}
	if !regularRepoFile(r, name) {
		return "source path is not a regular in-repository file: " + name
	}
	return ""
}

// Only identity is observed here. Sorted inert Python representations retain
// the same distinctions as json.dumps(sort_keys=True), including lone surrogates.
func coverageIdentityValue(value any) any {
	switch value := value.(type) {
	case *mapping:
		result := newMapping()
		for _, key := range sortedMappingKeys(value) {
			result.set(key, coverageIdentityValue(value.get(key)))
		}
		return result
	case []any:
		result := make([]any, len(value))
		for i, item := range value {
			result[i] = coverageIdentityValue(item)
		}
		return result
	default:
		return value
	}
}
