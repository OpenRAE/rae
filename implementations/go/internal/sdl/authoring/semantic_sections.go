package authoring

import (
	"encoding/json"
	"fmt"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type semanticEntity struct {
	Events   []string                  `json:"events"`
	Entities map[string]semanticEntity `json:"entities"`
	Role     *string                   `json:"role"`
}
type semanticEntityFact struct {
	name     string
	events   []string
	tokens   []string
	location source.Range
	located  bool
	role     *string
}
type semanticRole struct {
	name     string
	entities []string
}

func (m *semanticModel) entityFacts() error {
	var tree struct {
		Entities map[string]semanticEntity `json:"entities"`
	}
	if err := json.Unmarshal(m.document.modelBytes(), &tree); err != nil {
		return invalid()
	}
	m.entityNames = map[string]bool{}
	m.appendEntities(tree.Entities, m.document.source.View().Child(entitiesField), "", []string{entitiesField})
	return nil
}
func (m *semanticModel) appendEntities(values map[string]semanticEntity, view source.View, prefix string, tokens []string) {
	ranges := map[string]source.Range{}
	for _, pair := range view.Members() {
		name, _ := pair.Key.Scalar()
		if location, present := pair.Key.Range(); present {
			ranges[name] = location
		}
	}
	for _, key := range m.keys(tokens...) {
		name, value := prefix+key, values[key]
		path := appendPath(tokens, key)
		location, located := ranges[key]
		m.entityNames[name] = true
		m.entities = append(m.entities, semanticEntityFact{name: name, events: value.Events, tokens: path, location: location, located: located, role: value.Role})
		m.appendEntities(value.Entities, view.Child(key).Child(entitiesField), name+".", appendPath(path, entitiesField))
	}
}
func (m *semanticModel) roleFacts(name string, roles map[string]json.RawMessage) ([]semanticRole, error) {
	var result []semanticRole
	for _, role := range m.keys(nodesSection, name, "roles") {
		var value struct {
			Entities []string `json:"entities"`
		}
		if err := json.Unmarshal(roles[role], &value); err != nil {
			return nil, invalid()
		}
		result = append(result, semanticRole{role, value.Entities})
	}
	return result, nil
}

func (m *semanticModel) checkNarrative(c *semanticCollector) {
	m.checkEntities(c)
	m.checkInjects(c)
	m.checkEvents(c)
	m.checkScripts(c)
	m.checkStories(c)
	m.checkRoles(c)
}
func (m *semanticModel) checkEntities(c *semanticCollector) {
	for _, entity := range m.entities {
		owner := semanticOwner{entitiesField, entity.name}
		c.pointers[owner] = jsonpointer.FromTokens(entity.tokens)
		if entity.located {
			c.locations[owner] = entity.location
		}
		for _, ref := range entity.events {
			if !variable(ref) && !m.definitions[eventsSection][ref] {
				c.report(owner, fmt.Sprintf("Entity '%s' references undefined event '%s'", entity.name, ref))
			}
		}
	}
}
func (m *semanticModel) checkInjects(c *semanticCollector) {
	injects := fieldValue(m.transport.Injects)
	for _, name := range m.keys(injectsSection) {
		inject := injects[name]
		owner := semanticOwner{injectsSection, name}
		from := fieldValue(inject.FromEntity)
		if from != "" && !variable(from) && !m.entityNames[from] {
			c.report(owner, fmt.Sprintf("Inject '%s' from_entity '%s' is not a defined entity", name, from))
		}
		for _, ref := range fieldValue(inject.ToEntities) {
			if !variable(ref) && !m.entityNames[ref] {
				c.report(owner, fmt.Sprintf("Inject '%s' to_entity '%s' is not a defined entity", name, ref))
			}
		}
	}
}
func (m *semanticModel) checkEvents(c *semanticCollector) {
	events := fieldValue(m.transport.Events)
	for _, name := range m.keys(eventsSection) {
		for _, ref := range fieldValue(events[name].Injects) {
			if !variable(ref) && !m.definitions[injectsSection][ref] {
				c.report(semanticOwner{eventsSection, name}, fmt.Sprintf("Event '%s' references undefined inject '%s'", name, ref))
			}
		}
	}
}
func (m *semanticModel) checkScripts(c *semanticCollector) {
	for _, name := range m.keys(scriptsField) {
		for _, ref := range m.keys(scriptsField, name, eventsSection) {
			if !variable(ref) && !m.definitions[eventsSection][ref] {
				c.report(semanticOwner{scriptsField, name}, fmt.Sprintf("Script '%s' references undefined event '%s'", name, ref))
			}
		}
	}
}
func (m *semanticModel) checkStories(c *semanticCollector) {
	stories := fieldValue(m.transport.Stories)
	for _, name := range m.keys(storiesField) {
		for _, ref := range fieldValue(stories[name].Scripts) {
			if !variable(ref) && !m.definitions[scriptsField][ref] {
				c.report(semanticOwner{storiesField, name}, fmt.Sprintf("Story '%s' references undefined script '%s'", name, ref))
			}
		}
	}
}
func (m *semanticModel) checkRoles(c *semanticCollector) {
	for _, node := range m.nodes {
		for _, role := range node.roleDefinitions {
			for _, ref := range role.entities {
				if !variable(ref) && !m.entityNames[ref] {
					c.report(semanticOwner{nodesSection, node.name}, fmt.Sprintf("Node '%s' role '%s' references undefined entity '%s'", node.name, role.name, ref))
				}
			}
		}
	}
}
