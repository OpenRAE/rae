package authoring

import (
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

// Declaration enumeration is shared by formatting, semantic reference policy,
// and collision reporting. Structural tokens stay separate from rendered names.
func indexDeclarations(value map[string]any) *declarationIndex {
	return orderedDeclarations(value, nil)
}
func orderedDeclarations(value map[string]any, order map[string][]string) *declarationIndex {
	d := &declarationIndex{aliases: map[string]map[string]declaration{}, addresses: map[string]bool{}, declarations: map[string]declaration{}, order: order}
	d.add("scenario."+text(value["name"]), "", declaration{tokens: []string{"name"}, collisionKind: "scenario"})
	for _, section := range declarationSections() {
		if slices.Contains([]string{nodesSection, infrastructureField, entitiesField, contentField, workflowsSection, variablesSection}, section) {
			continue
		}
		d.section(section, value, false)
	}
	for _, field := range []string{toolAffordancesField, participantInjectDeliveriesField} {
		d.behaviorChildren(object(value[behaviorSection]), field)
	}
	d.section(variablesSection, value, false)
	d.section(nodesSection, value, true)
	d.section(infrastructureField, value, true)
	d.entities(object(value[entitiesField]), "", []string{entitiesField})
	d.section(contentField, value, true)
	d.section(workflowsSection, value, true)
	for i, raw := range array(value[forwardingSection]) {
		item := object(raw)
		d.add(forwardingSection+"."+text(item["forwarding_agent_id"]), "", declaration{target: true, authority: true, action: true, kind: forwardingSection, value: item, tokens: []string{forwardingSection, strconv.Itoa(i), "forwarding_agent_id"}, collisionKind: "forwarding-agent"})
	}
	for _, name := range d.keys(object(value[variationPointsField]), variationPointsField) {
		d.variationMembers(name, object(object(value[variationPointsField])[name]))
	}
	return d
}
func (d *declarationIndex) keys(value map[string]any, tokens ...string) []string {
	if keys, present := d.order[jsonpointer.FromTokens(tokens)]; present {
		return keys
	}
	keys := make([]string, 0, len(value))
	for key := range value {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	return keys
}
func declarationKind(section string) string {
	switch section {
	case nodesSection:
		return "node"
	case workflowsSection:
		return "workflow"
	case variablesSection:
		return "variable"
	default:
		return section
	}
}
func (d *declarationIndex) section(section string, value map[string]any, children bool) {
	entries := object(value[section])
	for _, name := range d.keys(entries, section) {
		alias := name
		if section == infrastructureField {
			alias = ""
		}
		category := sectionCategory(section)
		category.value, category.tokens, category.collisionKind = object(entries[name]), []string{section, name}, declarationKind(section)
		address := section + "." + name
		d.add(address, alias, category)
		if children {
			d.children(section, name, address, category.value)
		}
	}
}
func (d *declarationIndex) entities(entities map[string]any, prefix string, tokens []string) {
	for _, name := range d.keys(entities, tokens...) {
		qualified, item := prefix+name, object(entities[name])
		path := appendPath(tokens, name)
		d.add(entitiesField+"."+qualified, qualified, declaration{target: true, authority: true, action: true, kind: entitiesField, value: item, tokens: path, collisionKind: "entity"})
		d.entities(object(item[entitiesField]), qualified+".", appendPath(path, entitiesField))
	}
}
func (d *declarationIndex) children(section, name, address string, value map[string]any) {
	path := []string{section, name}
	switch section {
	case nodesSection:
		for _, role := range d.keys(object(value["roles"]), section, name, "roles") {
			d.add(address+".roles."+role, "", declaration{tokens: appendPath(appendPath(path, "roles"), role), collisionKind: "node-role"})
		}
		d.namedItems(array(value[servicesField]), address+".services.", false, servicesField, "service", appendPath(path, servicesField))
		if runtime := object(value["runtime"]); runtime != nil {
			d.runtime(runtime, runtimeDeclarationContext{prefix: address + ".runtime.", node: name, tokens: appendPath(path, "runtime")}, sdlrules.RuntimeFamilies())
		}
	case infrastructureField:
		d.namedItems(array(value["acls"]), address+".acls.", false, "acls", "infrastructure-acl", appendPath(path, "acls"))
	case contentField:
		d.namedItems(array(value["items"]), address+".items.", true, "content-item", "content-item", appendPath(path, "items"))
	case workflowsSection:
		for _, step := range d.keys(object(value["steps"]), section, name, "steps") {
			d.add(address+".steps."+step, name+"."+step, declaration{tokens: appendPath(appendPath(path, "steps"), step), collisionKind: "workflow-step"})
		}
	}
}
func (d *declarationIndex) behaviorChildren(values map[string]any, field string) {
	for _, name := range d.keys(values, behaviorSection) {
		for _, id := range d.keys(object(object(values[name])[field]), behaviorSection, name, field) {
			category := declaration{declared: true, collisionKind: "tool-affordance"}
			if field == participantInjectDeliveriesField {
				category = declaration{target: true, authority: true, collisionKind: "participant-inject-delivery"}
			}
			category.tokens = []string{behaviorSection, name, field, id}
			d.add(behaviorSection+"."+name+"."+field+"."+id, "", category)
		}
	}
}
func (d *declarationIndex) variationMembers(name string, value map[string]any) {
	container, kind := "members", "variation-member"
	if value[kindField] == "alternative" {
		container, kind = "alternatives", "variation-alternative"
	}
	for _, member := range d.keys(object(value[container]), variationPointsField, name, container) {
		d.add(variationPointsField+"."+name+"."+container+"."+member, name+"."+member, declaration{declared: true, tokens: []string{variationPointsField, name, container, member}, collisionKind: kind})
	}
}
func (d *declarationIndex) namedItems(items []any, prefix string, aliases bool, kind, label string, tokens []string) {
	for i, raw := range items {
		item := object(raw)
		name := text(item["name"])
		if name == "" {
			continue
		}
		alias := ""
		if aliases {
			alias = name
		}
		d.add(prefix+name, alias, declaration{target: true, authority: true, action: true, kind: kind, value: item, tokens: appendPath(appendPath(tokens, strconv.Itoa(i)), "name"), collisionKind: label})
	}
}

type runtimeDeclarationContext struct {
	prefix, parentKind, node, parent string
	owner                            map[string]any
	tokens                           []string
}

func (d *declarationIndex) runtime(value map[string]any, context runtimeDeclarationContext, specs []sdlrules.RuntimeCollection) {
	for _, spec := range specs {
		d.runtimeCollection(value, context, spec)
	}
}
func (d *declarationIndex) runtimeCollection(value map[string]any, context runtimeDeclarationContext, spec sdlrules.RuntimeCollection) {
	kind := spec.Collection
	if context.parentKind != "" {
		kind = context.parentKind + "." + kind
	}
	for i, raw := range array(value[spec.Collection]) {
		item := object(raw)
		address := context.prefix + spec.Collection + "." + text(item[spec.Identity])
		root := context.owner
		if root == nil {
			root = item
		}
		path := appendPath(appendPath(context.tokens, spec.Collection), strconv.Itoa(i))
		d.add(address, "", declaration{target: true, authority: true, action: true, kind: kind, node: context.node, parent: context.parent, value: item, owner: root, tokens: appendPath(path, spec.Identity), collisionKind: "runtime-" + spec.Collection})
		d.runtime(item, runtimeDeclarationContext{address + ".", kind, context.node, address, root, path}, spec.Children)
	}
}
