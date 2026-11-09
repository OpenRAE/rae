package authoring

import (
	"maps"
	"path"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

// Resolution headers are checked as native fragments. They stay private and do
// not grant phase admission or claim to be complete expansion evidence.
func (c *composition) addImportRecords(importer, name string, requested, descriptor map[string]any, raw []byte) error {
	exports, err := exportDigest(descriptor)
	if err != nil {
		return err
	}
	namespace := text(requested[namespaceField])
	header := map[string]any{
		namespaceField: []any{namespace}, "requested_source": importSource(requested), requestedVersionField: text(requested["version"]), "requested_digest": normalizedDigest(text(requested["digest"])),
		moduleIDField: descriptor["id"], moduleVersionField: descriptor["version"], resolvedSourceField: relativeSource(path.Dir(importer), name), contentDigestField: digest.SHA256(raw), exportHashField: exports,
	}
	header["bindings"] = c.facts[name].bindings
	// ImportDecl's absent version has a model default; explicit empty remains empty.
	if _, present := requested["version"]; !present {
		header[requestedVersionField] = "*"
	}
	additions := []map[string]any{header}
	for _, child := range c.records[name] {
		prefixed := maps.Clone(child)
		prefixed[namespaceField] = append([]any{namespace}, array(child[namespaceField])...)
		additions = append(additions, prefixed)
	}
	for _, record := range additions {
		if err = c.checkImportRecord(record); err != nil {
			return err
		}
	}
	return c.appendImportRecords(importer, additions)
}
func (c *composition) checkImportRecord(record map[string]any) error {
	data, err := toJSON(record)
	if err != nil {
		return err
	}
	limits := modelLimits(data)
	return c.parser.models.CheckModelFragment("instantiated-scenario-v1", "#/$defs/ResolvedImportProvenance", data, limits)
}
func (c *composition) appendImportRecords(importer string, additions []map[string]any) error {
	seen := map[string]bool{}
	for _, record := range c.records[importer] {
		seen[namespaceKey(record)] = true
	}
	for _, record := range additions {
		key := namespaceKey(record)
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	c.records[importer] = append(c.records[importer], additions...)
	return nil
}
func namespaceKey(record map[string]any) string {
	var parts []string
	for _, part := range array(record[namespaceField]) {
		parts = append(parts, text(part))
	}
	return strings.Join(parts, ".")
}
func normalizedDigest(value string) string {
	if len(value) == 64 {
		return sha256Prefix + value
	}
	return value
}
func exportDigest(descriptor map[string]any) (string, error) {
	exports := descriptor["exports"]
	if exports == nil {
		exports = map[string]any{}
	}
	encoded, err := toJSON(exports)
	if err != nil {
		return "", err
	}
	canonical, err := canonjson.Sorted(encoded, true)
	if err != nil {
		return "", err
	}
	return digest.SHA256(canonical), nil
}
func relativeSource(directory, target string) string {
	var base []string
	if directory != "." {
		base = strings.Split(directory, "/")
	}
	parts := strings.Split(target, "/")
	common := 0
	for common < len(base) && common < len(parts) && base[common] == parts[common] {
		common++
	}
	result := strings.Repeat("../", len(base)-common) + strings.Join(parts[common:], "/")
	result = strings.TrimSuffix(result, "/")
	if result == "" {
		return "."
	}
	return result
}
