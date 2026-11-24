package authoring

import (
	"fmt"
	"maps"
	"regexp"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type legacyClassification struct{ pointer, subject, identifier, declaration string }
type legacyClassifications struct {
	native       map[string]any
	digest       string
	records      []legacyClassification
	declarations map[string]string
}

var legacyCWE = regexp.MustCompile(`^CWE-[0-9]+$`)

func (p *Parser) legacyClassificationSource(data []byte) (*legacyClassifications, error) {
	options := source.DefaultOptions()
	options.Limits = p.limits
	options.RequireMapping = true
	document, err := source.Decode(data, options)
	if err != nil {
		return nil, err
	}
	original := object(document.Value())
	if revision, present := original["semantic_revision"]; present && revision != progressiveRevision {
		return nil, invalid()
	}
	if err = shorthands(original, map[string][]string{}); err != nil {
		return nil, err
	}
	if _, err = migrateVM(original, document, "reject", ""); err != nil {
		return nil, err
	}
	if nonemptyJSON(original[importsField]) {
		return nil, invalid()
	}
	if _, present := original["instantiation_provenance"]; present {
		return nil, invalid()
	}
	identity, err := jsonIdentity(map[string]any{termProfile: semanticProfile, termScenario: original, "module_variable_specs": map[string]any{}, "module_node_variable_refs": map[string]any{}})
	if err != nil {
		return nil, err
	}
	// Value is a detached projection. Its exact original digest is sealed
	// before classification fields are removed from this private candidate.
	native := original
	result := &legacyClassifications{native: native, digest: identity, records: []legacyClassification{}, declarations: map[string]string{}}
	if err = result.readDeclarations(); err != nil {
		return nil, err
	}
	delete(native, termVulnerabilities)
	for _, section := range []string{nodesSection, featuresSection, behaviorSection} {
		if err = result.extractSection(section); err != nil {
			return nil, err
		}
	}
	if err = result.extractEntities(object(native[entitiesField]), "/entities", "entities"); err != nil {
		return nil, err
	}
	if err = result.extractActionMappings(); err != nil {
		return nil, err
	}
	slices.SortFunc(result.records, func(a, b legacyClassification) int { return strings.Compare(a.pointer, b.pointer) })
	return result, nil
}

func (s *legacyClassifications) readDeclarations() error {
	raw, present := s.native[termVulnerabilities]
	if !present {
		return nil
	}
	declarations := object(raw)
	if declarations == nil {
		return invalid()
	}
	for id, raw := range declarations {
		value := object(raw)
		if !validLegacyVulnerability(value) {
			return invalid()
		}
		s.declarations[id] = text(value["class"])
	}
	return nil
}
func validLegacyVulnerability(value map[string]any) bool {
	if !closed(value, []string{nameField, "description", "class"}, []string{"technical"}) {
		return false
	}
	for _, field := range []string{nameField, "description", "class"} {
		if _, ok := value[field].(string); !ok {
			return false
		}
	}
	if !legacyCWE.MatchString(text(value["class"])) {
		return false
	}
	if technical, present := value["technical"]; present {
		if _, ok := technical.(bool); !ok && !variable(technical) {
			return false
		}
	}
	return true
}
func (s *legacyClassifications) extractSection(section string) error {
	fields := []string{termVulnerabilities}
	if section == behaviorSection {
		fields = []string{"ai_offensive_behavior_refs", "defensive_behavior_refs", "offensive_behavior_refs"}
	}
	for name, raw := range object(s.native[section]) {
		value := object(raw)
		if err := s.extractFields(value, jsonpointer.FromTokens([]string{section, name}), section+"."+name, fields); err != nil {
			return err
		}
		if section == nodesSection {
			if err := s.extractRoutes(name, value); err != nil {
				return err
			}
		}
	}
	return nil
}
func (s *legacyClassifications) extractFields(value map[string]any, pointer, subject string, fields []string) error {
	for _, field := range fields {
		raw, present := value[field]
		if !present {
			continue
		}
		items, ok := raw.([]any)
		if !ok {
			return invalid()
		}
		if err := s.extractFieldItems(items, pointer, subject, field); err != nil {
			return err
		}
		delete(value, field)
	}
	return nil
}
func (s *legacyClassifications) extractFieldItems(items []any, pointer, subject, field string) error {
	seen := map[string]bool{}
	for i, item := range items {
		identifier, ok := item.(string)
		if !ok || strings.TrimSpace(identifier) == "" || containsVariable(identifier) || seen[identifier] {
			return invalid()
		}
		seen[identifier] = true
		declaration := ""
		if field == termVulnerabilities || field == "vulnerability_refs" {
			concept, present := s.declarations[identifier]
			if !present {
				return invalid()
			}
			declaration, identifier = "vulnerabilities."+identifier, concept
		}
		s.records = append(s.records, legacyClassification{pointer + "/" + field + "/" + strconv.Itoa(i), subject, identifier, declaration})
	}
	return nil
}
func (s *legacyClassifications) extractEntities(entities map[string]any, pointer, subject string) error {
	for name, raw := range entities {
		value := object(raw)
		path, ref := pointer+"/"+jsonpointer.EscapeToken(name), subject+"."+name
		if err := s.extractFields(value, path, ref, []string{termVulnerabilities, "categories"}); err != nil {
			return err
		}
		if err := s.extractEntities(object(value[entitiesField]), path+"/entities", ref); err != nil {
			return err
		}
	}
	return nil
}
func (s *legacyClassifications) extractRoutes(node string, value map[string]any) error {
	for appIndex, raw := range array(object(value["runtime"])["applications"]) {
		application := object(raw)
		for routeIndex, raw := range array(application["routes"]) {
			route := object(raw)
			if _, present := route["vulnerability_refs"]; !present {
				continue
			}
			appID, routeID := text(application["application_id"]), text(route["route_id"])
			if appID == "" || routeID == "" || containsVariable(appID) || containsVariable(routeID) {
				return invalid()
			}
			pointer := fmt.Sprintf("/nodes/%s/runtime/applications/%d/routes/%d", jsonpointer.EscapeToken(node), appIndex, routeIndex)
			if err := s.extractFields(route, pointer, "nodes."+node+".runtime.applications."+appID+".routes."+routeID, []string{"vulnerability_refs"}); err != nil {
				return err
			}
		}
	}
	return nil
}
func (s *legacyClassifications) extractActionMappings() error {
	for name, raw := range object(s.native[actionsSection]) {
		action := object(raw)
		raw, present := action["external_mappings"]
		if !present {
			continue
		}
		mappings, ok := raw.([]any)
		if !ok {
			return invalid()
		}
		if err := s.extractActionMappingItems(name, mappings); err != nil {
			return err
		}
		delete(action, "external_mappings")
	}
	return nil
}

func (s *legacyClassifications) extractActionMappingItems(name string, mappings []any) error {
	for index, raw := range mappings {
		mapping := object(raw)
		if !closed(mapping, []string{"system", "identifier", "loss_label", "rationale"}, nil) {
			return invalid()
		}
		for _, field := range []string{"system", "identifier", "loss_label", "rationale"} {
			if strings.TrimSpace(text(mapping[field])) == "" {
				return invalid()
			}
		}
		identifier := text(mapping["identifier"])
		if containsVariable(identifier) {
			return invalid()
		}
		s.records = append(s.records, legacyClassification{fmt.Sprintf("/action_contracts/%s/external_mappings/%d", jsonpointer.EscapeToken(name), index), actionsSection + "." + name, identifier, ""})
	}
	return nil
}
func (s *legacyClassifications) declarationIDs() []string {
	result := []string{}
	for _, id := range slices.Sorted(maps.Keys(s.declarations)) {
		result = append(result, "vulnerabilities."+id)
	}
	return result
}
