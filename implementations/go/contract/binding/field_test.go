package binding

import (
	"encoding/json"
	"testing"
)

func TestFieldStates(t *testing.T) {
	type sample struct {
		Value Field[json.Number] `json:"value,omitzero"`
	}
	for _, raw := range []string{`{}`, `{"value":null}`, `{"value":0}`, `{"value":1.0}`, `{"value":123456789012345678901234567890}`} {
		var got sample
		if err := json.Unmarshal([]byte(raw), &got); err != nil {
			t.Fatal(err)
		}
		encoded, err := json.Marshal(got)
		if err != nil {
			t.Fatal(err)
		}
		if string(encoded) != raw {
			t.Errorf("Marshal(%s) = %s, want %s", raw, encoded, raw)
		}
	}
}

func TestFieldAccess(t *testing.T) {
	var field Field[int]
	if field.Present() || field.Null() {
		t.Error("zero field is present")
	}
	if _, ok := field.Value(); ok {
		t.Error("zero field has a value")
	}
	if err := json.Unmarshal([]byte(`null`), &field); err != nil {
		t.Fatal(err)
	}
	if !field.Present() || !field.Null() {
		t.Error("null field lost its supplied state")
	}
	if _, ok := field.Value(); ok {
		t.Error("null field has a value")
	}
	if err := json.Unmarshal([]byte(`0`), &field); err != nil {
		t.Fatal(err)
	}
	if got, ok := field.Value(); !ok || got != 0 {
		t.Errorf("Value() = (%d,%v), want (0,true)", got, ok)
	}
	if err := json.Unmarshal([]byte(`"invalid"`), &field); err == nil {
		t.Error("UnmarshalJSON(string as integer) = nil, want refusal")
	}
}
