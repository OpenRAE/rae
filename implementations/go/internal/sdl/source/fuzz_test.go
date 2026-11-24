package source

import (
	"encoding/json"
	"testing"
)

// CI executes fuzzing. These seeds also retain the graph and escape refusals.
func FuzzDecode(f *testing.F) {
	for _, seed := range []string{"name: safe\n", "a: &a [*a]\n", "a: [x, y]\n", "value: \"\\uD800\"\n", "? [x, y]\n: z\n", "a: &a {x: y}\nb: {<<: *a}\n", string([]byte{0xff}), "a: \x00\n"} {
		f.Add([]byte(seed))
	}
	f.Fuzz(func(t *testing.T, data []byte) {
		options := DefaultOptions()
		options.Limits.MaxInputBytes = 16384
		options.Limits.MaxScalarBytes = 4096
		options.Limits.MaxNodes = 1024
		options.Limits.MaxExpandedNodes = 2048
		options.Limits.MaxAliases = 32
		options.Limits.MaxDepth = 32
		document, err := Decode(data, options)
		if err != nil {
			return
		}
		if _, marshalErr := json.Marshal(document.Value()); marshalErr != nil {
			t.Fatalf("Decode() returned a non-JSON value: %v", marshalErr)
		}
		rendered, err := document.Render(32768)
		if err == nil && len(rendered) > 32768 {
			t.Fatal("Render() exceeded the output reservation")
		}
	})
}
