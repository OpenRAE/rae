package validation

import (
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func FuzzSchemaBoundary(f *testing.F) {
	v, err := New(nil)
	if err != nil {
		f.Fatal(err)
	}
	f.Add([]byte(`{}`))
	f.Add([]byte(`{"invariants":[null]}`))
	f.Add([]byte(`{"profile_id":"raes-semantic-invariants-v1","schema_version":"raes-semantic-invariants/v1","keyword":"x-raes-invariants","uri":"https://openrae.github.io/rae/schemas/semantic-invariants/v1","invariant_entry_schema":"#/$defs/RaesSemanticInvariantEntryModel","profile_reference_schema":"#/$defs/RaesSemanticInvariantProfileReferenceModel","invariants":[]}`))
	f.Fuzz(func(t *testing.T, data []byte) {
		limits := ingress.Limits{MaxBytes: 4096, MaxDepth: 32}
		if err := v.CheckSchema("raes-semantic-invariants-v1", data, limits); err != nil {
			return
		}
		if _, err := v.DecodeSchema("raes-semantic-invariants-v1", data, limits); err != nil {
			t.Fatalf("schema-valid input failed its binding: %v", err)
		}
	})
}
