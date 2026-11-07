package admission

import "slices"

func sdlDatabaseService(v any) error {
	if err := sdlUniqueCollections([2]string{"databases", "database_id"}, [2]string{termRoles, "role_id"}, [2]string{termSettings, termName})(v); err != nil {
		return err
	}
	schemas, tables := []any{}, []any{}
	for _, database := range array(at(v, "databases")) {
		for _, schema := range array(at(database, "schemas")) {
			schemas = append(schemas, schema)
			tables = append(tables, array(at(schema, "tables"))...)
		}
	}
	if !sdlUniqueKey(schemas, "schema_id", false) || !sdlUniqueKey(tables, "table_id", false) {
		return invalid()
	}
	return sdlDatabaseProtocol(v)
}
func sdlDatabaseProtocol(v any) error {
	protocol := stringAt(v, "protocol")
	if protocol == "" || protocol == statusUnknown || variableRef(protocol) {
		return nil
	}
	allowed := map[string][]string{"postgresql": {"postgresql"}, termMySQL: {termMySQL}, "mariadb": {termMySQL}, "mssql": {"tds"}, "mongodb": {"mongodb"}, "redis": {"redis"}}
	choices, known := allowed[stringAt(v, "engine")]
	if !known {
		return nil
	}
	return require(slices.Contains(choices, protocol))
}
func sdlDatabaseGrant(v any) error {
	privileges := stringsOf(at(v, "privileges"))
	if len(privileges) == 0 || !unique(privileges) || !nonblankSDLFields(v, "grantee_role_ref", "object_ref") {
		return invalid()
	}
	return require(!slices.ContainsFunc(privileges, sdlBlank))
}
