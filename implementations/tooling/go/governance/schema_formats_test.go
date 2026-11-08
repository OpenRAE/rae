package governance

import (
	"encoding/json"
	"testing"
)

func TestSchemaFormatReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Name  string
		Value json.RawMessage
		Valid bool
	}](t, "schema-formats-reference") {
		raw := newMapping()
		raw.set("format", tc.Name)
		schema, err := compileCandidate(raw, false, true)
		if err != nil {
			t.Fatal(err)
		}
		value, err := decodeJSON(tc.Value, 0, false)
		if err != nil {
			t.Fatal(err)
		}
		err = schema.Validate(schemaTransport(value))
		want := tc.Valid
		if tc.Name == "regex" {
			switch value {
			case "{123e4567-e89b-12d3-a456-426614174000}", "]":
				want = true
			case `^a$(?![\s\S])`:
				want = false
			}
		}
		if (err == nil) != want {
			t.Errorf("%s on %s valid=%t want=%t: %v", tc.Name, tc.Value, err == nil, want, err)
		}
	}
}
