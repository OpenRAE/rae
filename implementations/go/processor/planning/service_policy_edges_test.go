package planning

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func TestServiceMaterializationRequiresProfileExactSupportAndReadbackTogether(t *testing.T) {
	for _, profile := range []string{"service-content", "service-search-index-schema"} {
		term, kind := "service-content-v1", "service-content-materialization"
		if profile == "service-search-index-schema" {
			term, kind = "service-search-index-schema-v1", "service-search-index-schema-materialization"
		}
		for _, test := range []struct {
			name                     string
			profile, exact, readback bool
			want                     string
		}{
			{"profile absent", false, true, true, "provisioner.unsupported-service-materialization-profile"},
			{"exact absent", true, false, true, "realization.unsupported-exact-requirement"},
			{"readback absent", true, true, false, "provisioner.service-materialization-readback-unsupported"},
			{"supported", true, true, true, ""},
		} {
			t.Run(profile+"/"+test.name, func(t *testing.T) {
				code, _, err := serviceMaterializationGap(&processor.ServiceMaterialization{InterfaceProfile: profile}, map[string]bool{`"` + term + `"`: test.profile}, map[string]bool{kind: test.exact}, test.readback)
				if err != nil || code != test.want {
					t.Fatalf("service support=%q %v, want %q", code, err, test.want)
				}
			})
		}
	}
}

func privateServiceProfile(t *testing.T) binding.DomainProfileBindingV1 {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/plans/plan-realization-profiles-v1/valid/resource-label-authority.json")
	if err != nil {
		t.Fatal(err)
	}
	var authority binding.PlanRealizationProfilesV1
	if parseErr := json.Unmarshal(raw, &authority); parseErr != nil {
		t.Fatal(parseErr)
	}
	rows := fieldValue(authority.Bindings)
	if len(rows) != 1 {
		t.Fatal("profile fixture changed")
	}
	var profile binding.DomainProfileBindingV1
	if bindingErr := json.Unmarshal(rawProjection(rows[0]), &profile); bindingErr != nil {
		t.Fatal(bindingErr)
	}
	return profile
}

func TestPrivateServiceProfilesUseTheirExactCanonicalCoordinate(t *testing.T) {
	profile := privateServiceProfile(t)
	coordinate, err := json.Marshal(fieldValue(profile.Coordinate))
	if err != nil {
		t.Fatal(err)
	}
	canonical, err := canonjson.JCS(coordinate)
	if err != nil {
		t.Fatal(err)
	}
	service := processor.ServiceMaterialization{ProfileBinding: &profile}
	if code, _, err := serviceMaterializationGap(&service, map[string]bool{string(canonical): true}, nil, false); err != nil || code != "" {
		t.Fatalf("exact private coordinate refused: %q %v", code, err)
	}
	if code, _, err := serviceMaterializationGap(&service, map[string]bool{}, nil, false); err != nil || code != "provisioner.unsupported-service-materialization-profile" {
		t.Fatal("unlisted private profile accepted")
	}
}

func TestServiceReadbackNeedsRealizedIndependentObservation(t *testing.T) {
	for _, test := range []struct {
		kind, disposition, strength string
		want                        bool
	}{
		{"content-placement", "realized", "guest-observed", true}, {"content-placement", "realized", "daemon-observed", true},
		{"content-placement", "realized", "controller-reported", false}, {"content-placement", "unresolved", "guest-observed", false}, {"node-type", "realized", "guest-observed", false},
	} {
		t.Run(test.kind+"/"+test.strength+"/"+test.disposition, func(t *testing.T) {
			var envelope binding.RealizationEnvelopeV1
			raw, err := json.Marshal(map[string]any{"concerns": []any{map[string]any{"concern": test.kind, "disposition": test.disposition, "observation_strength": test.strength}}})
			if err != nil {
				t.Fatal(err)
			}
			if err := json.Unmarshal(raw, &envelope); err != nil {
				t.Fatal(err)
			}
			if got := independentServiceReadback(&envelope); got != test.want {
				t.Fatalf("independent readback=%t, want %t", got, test.want)
			}
		})
	}
	if independentServiceReadback(nil) {
		t.Fatal("missing envelope supplied readback authority")
	}
}
