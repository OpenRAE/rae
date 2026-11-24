package authoring

import "fmt"

type semanticDatabaseRole struct {
	ID string `json:"role_id"`
}
type semanticDatabaseService struct {
	ID        string                  `json:"database_service_id"`
	Service   string                  `json:"service"`
	Roles     []semanticDatabaseRole  `json:"roles"`
	Databases []semanticDatabase      `json:"databases"`
	Grants    []semanticDatabaseGrant `json:"grants"`
}
type semanticDatabase struct {
	ID      string                   `json:"database_id"`
	Schemas []semanticDatabaseSchema `json:"schemas"`
}
type semanticDatabaseSchema struct {
	ID     string `json:"schema_id"`
	Tables []struct {
		ID string `json:"table_id"`
	} `json:"tables"`
}
type semanticDatabaseGrant struct {
	Role   string `json:"grantee_role_ref"`
	Kind   string `json:"object_type"`
	Object string `json:"object_ref"`
}

func (m *semanticModel) checkRuntimeDatabases(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, service := range node.runtime.Databases {
			check.database(service)
		}
	}
}
func (r semanticRuntimeCheck) database(service semanticDatabaseService) {
	label := fmt.Sprintf("Node '%s' runtime database service '%s'", r.node.name, service.ID)
	r.ownedService(label, service.Service)
	roles := map[string]bool{}
	for _, role := range service.Roles {
		roles[role.ID] = true
	}
	objects := service.objects()
	for _, grant := range service.Grants {
		if !variable(grant.Role) && !roles[grant.Role] {
			r.reportf(label, "grant grantee_role_ref '%s' is not a role in the service", grant.Role)
		}
		if !variable(grant.Object) && !variable(grant.Kind) && !objects[grant.Kind][grant.Object] {
			r.reportf(label, "grant object_ref '%s' is not a %s in the service", grant.Object, grant.Kind)
		}
	}
}
func (service semanticDatabaseService) objects() map[string]map[string]bool {
	objects := map[string]map[string]bool{"database": {}, "schema": {}, "table": {}}
	for _, db := range service.Databases {
		objects["database"][db.ID] = true
		for _, schema := range db.Schemas {
			objects["schema"][schema.ID] = true
			for _, table := range schema.Tables {
				objects["table"][table.ID] = true
			}
		}
	}
	return objects
}

type semanticDNSService struct {
	ID            string   `json:"dns_service_id"`
	Service       string   `json:"service"`
	Configuration []string `json:"configuration_file_refs"`
	Logs          []string `json:"log_file_refs"`
	Zones         []struct {
		ID    string   `json:"zone_id"`
		Files []string `json:"zone_file_refs"`
	} `json:"zones"`
}

func (m *semanticModel) checkRuntimeDNS(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, service := range node.runtime.DNS {
			label := fmt.Sprintf("Node '%s' runtime DNS service '%s'", node.name, service.ID)
			check.ownedService(label, service.Service)
			check.files(label, "configuration_file_refs", service.Configuration)
			check.files(label, "log_file_refs", service.Logs)
			for _, zone := range service.Zones {
				check.files(label+" zone '"+zone.ID+"'", "zone_file_refs", zone.Files)
			}
		}
	}
}
