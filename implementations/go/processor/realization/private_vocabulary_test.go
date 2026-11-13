package realization

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestPrivateDNSNumericIdentityStaysExactUnderOpenParent(t *testing.T) {
	compiled := compileRealizationFixture(t, `name: numeric-identity
realization: {default: open}
nodes:
  host:
    type: compute
    runtime:
      dns_services:
        - dns_service_id: dns
          zones:
            - zone_id: zone
              name: example.test
              rrsets:
                - rrset_id: record
                  owner: example.test
                  record_type: other
                  type_code: 65280
                  records: [{rdata: opaque-content}]
`)
	requirement := privateDNSRequirement(t, compiled)
	raw := requireType[[]any](t, requirement.source.value.Document())
	projection, err := ProjectConcern(requirement.Kind, selectionTestValue(t, raw), false, true)
	if err != nil {
		t.Fatal(err)
	}
	actual := requireType[[]any](t, projection.Document())
	if !privateDNSAdmits(t, requirement, actual) {
		t.Fatal("authored private DNS identity refused")
	}
	zones := requireType[[]any](t, requireType[map[string]any](t, actual[0])["zones"])
	rrsets := requireType[[]any](t, requireType[map[string]any](t, zones[0])["rrsets"])
	requireType[map[string]any](t, rrsets[0])["type_code"] = json.Number("65281")
	if privateDNSAdmits(t, requirement, actual) {
		t.Fatal("open parent widened private DNS type identity")
	}
}
func privateDNSRequirement(t *testing.T, compiled Resolution) Requirement {
	t.Helper()
	for _, requirement := range compiled.Requirements {
		if requirement.Kind == "runtime-dns-services" {
			if requirement.Constraint == nil {
				t.Fatal("private DNS identity lost constraint")
			}
			return requirement
		}
	}
	t.Fatal("missing DNS requirement")
	return Requirement{}
}
func privateDNSAdmits(t *testing.T, requirement Requirement, input []any) bool {
	t.Helper()
	checked, err := admission.EvaluateRealizationConstraint(requirement.Constraint, selectionTestValue(t, input), admission.DefaultConstraintLimits())
	if err != nil {
		t.Fatal(err)
	}
	return requireType[map[string]any](t, checked.Document())["status"] == "conformant"
}
