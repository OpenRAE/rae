package admission

import "testing"

func TestProcessCapabilityUsesSharedFiniteDomainRules(t *testing.T) {
	v, err := New()
	if err != nil {
		t.Fatal(err)
	}
	capability := constraintTestValue(t, v, `{"resource":"open_file_descriptors","scopes":["process"],"minimum":10,"maximum":100,"supports_unlimited":false}`)
	for _, tt := range []struct {
		soft, hard string
		want       bool
	}{{`[20]`, `[50]`, true}, {`[10,20,100]`, `[100]`, true}, {`[9,20]`, `[100]`, false}, {`[20]`, `["unlimited"]`, false}, {`[]`, `[]`, true}} {
		var soft, hard Fragment
		if tt.soft != "" {
			soft = constraintTestValue(t, v, tt.soft)
		}
		if tt.hard != "" {
			hard = constraintTestValue(t, v, tt.hard)
		}
		got, err := ProcessResourceLimitCapabilityAdmits(v, capability, "open_file_descriptors", "process", soft, hard)
		if err != nil || got != tt.want {
			t.Fatalf("soft=%s hard=%s: %v %v", tt.soft, tt.hard, got, err)
		}
	}
	if _, err := ProcessResourceLimitCapabilityAdmits(v, replacedConstraintFragment{capability}, "open_file_descriptors", "process", nil, nil); err == nil {
		t.Fatal("foreign capability accepted")
	}
}
