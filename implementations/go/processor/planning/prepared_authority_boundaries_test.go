package planning

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

func TestPreparedProfileAuthorityCannotBeInventedOrReassigned(t *testing.T) {
	var profile binding.DomainProfileBindingV1
	if err := json.Unmarshal([]byte(`{"owner":{"canonical_address":"#/resources/provision.node.host"}}`), &profile); err != nil {
		t.Fatal(err)
	}
	selection := preparedSelection{original: &executionPlan{}}
	if violation, err := selection.profileViolation(); err != nil || violation != "" {
		t.Fatal("empty profile selection refused")
	}
	selection.operations = []planOperation{{Address: "provision.node.host", Action: "create", Profiles: []binding.DomainProfileBindingV1{profile}}}
	if violation, err := selection.profileViolation(); err != nil || violation != "Backend preparation invented profile authority." {
		t.Fatalf("invented authority accepted: %q %v", violation, err)
	}
	selection.operations[0].Action = termDelete
	if violation, _ := selection.profileViolation(); violation != "Backend preparation changed a profile owner." {
		t.Fatal("deleted profile owner accepted")
	}
	selection.operations[0].Action = "create"
	selection.operations[0].Address = "provision.node.other"
	if violation, _ := selection.profileViolation(); violation != "Backend preparation changed a profile owner." {
		t.Fatal("reassigned profile owner accepted")
	}
	selection.operations[0].Address = "provision.node.host"
	selection.original.profileAuthority = &binding.PlanRealizationProfilesV1{}
	if violation, _ := selection.profileViolation(); violation != "Backend preparation returned invalid profile bindings." {
		t.Fatal("missing independent profile context accepted")
	}
	selection.original.context.ProfileContext = &binding.DomainProfileResolutionContextV1{}
	if violation, _ := selection.profileViolation(); violation != "Backend preparation returned invalid profile bindings." {
		t.Fatal("invalid independent profile context accepted")
	}
}

func TestPreparedOSDeliveryReadsOnlyMatchingObservationField(t *testing.T) {
	authority := realization.Authority{Address: "provision.node.host", Domain: "provisioning", Concern: termOsFamily}
	for _, test := range []struct {
		name, observation string
		want              any
		present           bool
	}{
		{"absent", ``, "fallback", true},
		{"matched", `{"address":"provision.node.host","domain":"provisioning","requirement_kind":"operating-system","operating_system":{"family":"linux"}}`, "linux", true},
		{"other address", `{"address":"provision.node.other","domain":"provisioning","requirement_kind":"operating-system","operating_system":{"family":"windows"}}`, "fallback", true},
		{"other domain", `{"address":"provision.node.host","domain":"evaluation","requirement_kind":"operating-system","operating_system":{"family":"windows"}}`, "fallback", true},
		{"other kind", `{"address":"provision.node.host","domain":"provisioning","requirement_kind":"other","operating_system":{"family":"windows"}}`, "fallback", true},
		{"missing field", `{"address":"provision.node.host","domain":"provisioning","requirement_kind":"operating-system","operating_system":{}}`, nil, false},
		{"invalid field", `{"address":"provision.node.host","domain":"provisioning","requirement_kind":"operating-system","operating_system":{"family":true}}`, nil, false},
		{"invalid identity", `{"address":"provision.node.host","domain":"provisioning","requirement_kind":"operating-system","operating_system":[]}`, "fallback", true},
		{"null identity", `{"address":"provision.node.host","domain":"provisioning","requirement_kind":"operating-system","operating_system":null}`, "fallback", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			rows := test.observation
			var snapshot binding.RuntimeSnapshotV1
			if err := json.Unmarshal([]byte(`{"schema_version":"runtime-snapshot/v1","entries":{},"realization_observations":[`+rows+`]}`), &snapshot); err != nil {
				t.Fatal(err)
			}
			value, present := preparedDeliveredValue(authority, snapshot, "fallback", true)
			if value != test.want || present != test.present {
				t.Fatalf("delivered value=%v/%t, want %v/%t", value, present, test.want, test.present)
			}
		})
	}
	authority.Concern = "runtime-dns"
	if value, present := preparedDeliveredValue(authority, binding.RuntimeSnapshotV1{}, "dns", true); value != "dns" || !present {
		t.Fatal("non-OS readback lost its native fallback")
	}
}
