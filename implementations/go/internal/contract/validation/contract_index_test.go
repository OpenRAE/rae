package validation

import "testing"

func TestContractInventoryQueryDoesNotGrantAdmission(t *testing.T) {
	v, err := New(nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(v.contracts) != 148 {
		t.Fatal("publication inventory changed")
	}
	for id := range v.contracts {
		if !v.HasContract(id) {
			t.Error("published contract omitted", id)
		}
	}
	for _, owner := range []*Validator{nil, {}, v} {
		if owner.HasContract("") || owner.HasContract("unknown-contract-v1") {
			t.Fatal("unknown contract reported as published")
		}
	}
	if (&Validator{}).HasContract("sdl-authoring-input-v1") {
		t.Fatal("uncompiled validator reported a publication")
	}
}
