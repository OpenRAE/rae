package admission

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestObservationNormalizationRetainsIndependentProhibitions(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	var document binding.ObservationDemandV1
	raw := []byte(`{"schema_version":"observation-demand/v1","document_id":"example","scope_profile":"recursive-realization-constraint/v1","rules":[{"rule_id":"selected","scope":"/nodes/server","purpose":"experimental","mode":"selected","selector":{"semantic_scope":"/nodes/server","data_kind":"stream","names":["events"]},"collection":"require","redaction":"none","integrity":"checksum","authority_ref":"author"},{"rule_id":"privacy","scope":"","purpose":"experimental","collection":"forbid","authority_ref":"privacy","required":true}]}`)
	if json.Unmarshal(raw, &document) != nil {
		t.Fatal("document")
	}
	result, err := NormalizeObservationDemands(owner, document, []string{"/nodes/server"}, DefaultConstraintLimits())
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Effective) != 1 {
		t.Fatalf("result=%+v", result)
	}
	effective := result.Effective[0]
	if err := CheckFragment(effective, EffectiveObservationDemand); err != nil {
		t.Fatal(err)
	}
	value := requireType[map[string]any](t, effective.Document())
	prohibited := requireType[[]any](t, value["prohibited_stages"])
	if len(prohibited) != 1 || prohibited[0] != "collection" {
		t.Fatalf("lost independent prohibition: %+v", value)
	}
	if _, err := NormalizeObservationDemands(owner, document, []string{"/nodes/server", "/nodes/server"}, DefaultConstraintLimits()); err == nil {
		t.Fatal("duplicate scopes accepted")
	}
}
