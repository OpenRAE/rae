package parity

import (
	"encoding/json"
	"testing"
)

func TestSchemaRunner(t *testing.T) {
	run := schemaRunner()
	for _, test := range []struct {
		input string
		valid bool
	}{{`{"name":"example"}`, true}, {`{"name":1}`, false}, {`{`, false}} {
		got, err := run(t.Context(), Case{Args: []string{"sdl-authoring-input-v1"}, Files: map[string][]byte{"payload.json": []byte(test.input)}})
		if err != nil {
			t.Fatal(err)
		}
		var result struct {
			Valid bool `json:"valid"`
		}
		if err := json.Unmarshal(got, &result); err != nil {
			t.Fatal(err)
		}
		if result.Valid != test.valid {
			t.Errorf("schema(%s) = %s, want valid=%v", test.input, got, test.valid)
		}
	}
}
