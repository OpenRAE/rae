package authoring

func operatingScopeIndex(value map[string]any) *declarationIndex {
	index := &declarationIndex{aliases: map[string]map[string]declaration{}, addresses: map[string]bool{}, declarations: map[string]declaration{}}
	category := declaration{target: true}
	for name, raw := range object(value[nodesSection]) {
		node := object(raw)
		if node["type"] == computeType {
			index.add(nodesPrefix+name, name, category)
		}
		if node["type"] == switchType && object(value[infrastructureField])[name] != nil {
			index.add("infrastructure."+name, name, category)
		}
		index.namedItems(array(node[servicesField]), nodesPrefix+name+".services.", true, servicesField, "service", []string{nodesSection, name, servicesField})
	}
	for name, raw := range object(value[contentField]) {
		index.add("content."+name, name, category)
		index.namedItems(array(object(raw)["items"]), "content."+name+".items.", true, "content-item", "content-item", []string{contentField, name, "items"})
	}
	return index
}
