package admission

func sdlDatastoreNode(v any) error {
	if !fieldsUnique(v, termRoles) || numericGreater(at(v, "heap_init_bytes"), at(v, "heap_max_bytes")) {
		return invalid()
	}
	return sdlUniqueCollections([2]string{"plugins", "plugin_id"}, [2]string{"endpoints", "endpoint_id"})(v)
}
func sdlDatastoreService(v any) error {
	if !sdlSymbolField(v, "datastore_service_id") || !fieldsUnique(v, "aliases", "lifecycle_policies", "ingest_pipelines", "pubsub_channels", "queues_streams", "backup_targets") || !unique(sdlDatastoreIDs(v)) {
		return invalid()
	}
	if stringAt(v, "data_model") == "key_value" {
		for _, partition := range array(at(v, "partitions")) {
			kind := stringAt(partition, termKind)
			if kind == "keyspace" || kind == "column_family" {
				return invalid()
			}
		}
	}
	return sdlDatastoreReferences(v)
}
func sdlDatastoreReferences(v any) error {
	for _, relation := range [][4]string{{fieldMappings, "partition_ref", "partitions", "partition_id"}, {"templates", "mapping_ref", fieldMappings, termMappingID}} {
		targets := rowSet(at(v, relation[2]), relation[3])
		for _, row := range array(at(v, relation[0])) {
			reference := stringAt(row, relation[1])
			if reference != "" && !variableRef(reference) && !targets[reference] {
				return invalid()
			}
		}
	}
	return nil
}
func sdlDatastoreIDs(v any) []string {
	ids := []string{stringAt(v, "datastore_service_id")}
	for _, pair := range [][2]string{{"cluster", "cluster_id"}, {"persistence", "persistence_id"}, {"transport_security", "transport_security_id"}} {
		if value := at(v, pair[0]); value != nil {
			ids = append(ids, stringAt(value, pair[1]))
		}
	}
	for _, pair := range [][2]string{{termNodes, "node_id"}, {"partitions", "partition_id"}, {"templates", "template_id"}, {fieldMappings, termMappingID}, {termSettings, termSettingID}} {
		for _, row := range array(at(v, pair[0])) {
			ids = append(ids, stringAt(row, pair[1]))
		}
	}
	for _, node := range array(at(v, termNodes)) {
		for _, pair := range [][2]string{{"plugins", "plugin_id"}, {"endpoints", "endpoint_id"}} {
			for _, row := range array(at(node, pair[0])) {
				ids = append(ids, stringAt(row, pair[1]))
			}
		}
	}
	return ids
}
