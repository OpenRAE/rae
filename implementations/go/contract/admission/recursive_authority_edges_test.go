package admission

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func TestResourcePoolIdentityKeepsPrivateCoordinateOrderAndRefusesNonJSON(t *testing.T) {
	coordinate := map[string]any{"namespace": "example", "authority": "owner", "profile_id": "quota", "revision": "1", "definition_digest": "sha256:abc"}
	pool := map[string]any{"pool_ref": "pool", "owner_kind": "participant", "owner_ref": "worker", "resource_kind": coordinate, "unit": "items", "accounting_mode": "lease", "meter_profile_ref": nil}
	want := "participant-resource-pool:" + digest.SHA256([]byte(`["pool","participant","worker",{"namespace":"example","authority":"owner","profile_id":"quota","revision":"1","definition_digest":"sha256:abc"},"items","lease",null]`))
	identity, err := resourcePoolIdentity(pool)
	if err != nil || identity != want {
		t.Fatalf("pool identity changed: %q %v", identity, err)
	}
	coordinate["authority"] = func() {}
	if _, err := resourcePoolIdentity(pool); err == nil {
		t.Fatal("non-JSON private coordinate accepted")
	}
	pool["resource_kind"] = "cpu"
	pool["unit"] = func() {}
	if _, err := resourcePoolIdentity(pool); err == nil {
		t.Fatal("non-JSON pool identity accepted")
	}
}

func TestDescriptiveConstraintChildrenCannotGrantAuthoredOrClosedAuthority(t *testing.T) {
	literal := map[string]any{"kind": "literal", "origin": "observation", "value": "observed"}
	for _, test := range []struct {
		name  string
		value map[string]any
		valid bool
	}{
		{"literal", literal, true},
		{"record", map[string]any{"kind": "recursive-record", "origin": "backend", "fields": map[string]any{"name": literal}}, true},
		{"sequence", map[string]any{"kind": "sequence", "origin": "observation", "items": []any{literal}}, true},
		{"author cannot describe", map[string]any{"kind": "literal", "origin": "author"}, false},
		{"optional cannot describe", map[string]any{"kind": "literal", "origin": "backend", "presence": "optional"}, false},
		{"closed cannot describe", map[string]any{"kind": "recursive-record", "origin": "backend", "closure": map[string]any{"posture": "closed"}}, false},
		{"cardinality cannot constrain", map[string]any{"kind": "sequence", "origin": "backend", "min_items": json4096}, false},
		{"domain cannot describe", map[string]any{"kind": "domain", "origin": "observation"}, false},
		{"aliases cannot describe", map[string]any{"kind": "keyed-collection", "origin": "backend", "aliases": []any{map[string]any{}}}, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			if err := descriptiveValue(test.value); (err == nil) != test.valid {
				t.Fatalf("description authority=%v, want valid=%t", err, test.valid)
			}
		})
	}
}

func TestScalarNormalizationCannotHideNestedCollectionsOrConjunctions(t *testing.T) {
	for _, test := range []struct {
		rule  map[string]any
		valid bool
	}{
		{map[string]any{"kind": "all-of", "constraints": []any{map[string]any{"kind": "literal", "value": true}, map[string]any{"kind": "domain"}}}, true},
		{map[string]any{"kind": "all-of", "constraints": []any{map[string]any{"kind": "all-of", "constraints": []any{}}}}, false},
		{map[string]any{"kind": "all-of", "constraints": []any{true}}, false},
		{map[string]any{"kind": "all-of", "constraints": []any{map[string]any{"kind": "recursive-record"}}}, false},
		{map[string]any{"kind": "all-of", "constraints": make([]any, 257)}, false},
		{map[string]any{"kind": "all-of", "constraints": "invalid"}, false},
	} {
		if scalarNormalizationRule(test.rule) != test.valid {
			t.Fatalf("non-scalar normalization authority: %+v", test.rule)
		}
	}
}
