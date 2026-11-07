package authoring

import (
	"encoding/json"
	"io/fs"
)

// Published manifest enums are the existing source of evidence-contract
// membership. Keep this set separate from the set of all packaged schemas.
func manifestEvidenceContracts(packaged fs.FS) (map[string]bool, error) {
	result := map[string]bool{}
	for _, entry := range [][2]string{{"processor-manifest", "processor-manifest-v2"}, {"backend-manifest", "backend-manifest-v2"}, {"participant-implementation-manifest", "participant-implementation-manifest-v1"}} {
		raw, err := fs.ReadFile(packaged, "schemas/"+entry[0]+"/"+entry[1]+".json")
		if err != nil {
			return nil, err
		}
		var schema map[string]any
		if err = json.Unmarshal(raw, &schema); err != nil {
			return nil, err
		}
		versions := object(object(schema["properties"])["supported_contract_versions"])
		enums := array(object(versions["items"])["enum"])
		if len(enums) == 0 {
			return nil, invalid()
		}
		for _, value := range enums {
			result[text(value)] = true
		}
	}
	return result, nil
}
