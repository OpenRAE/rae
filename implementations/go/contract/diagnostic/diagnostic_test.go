package diagnostic

import (
	"encoding/json"
	"testing"
)

func TestOriginalPointerIsOptionalMetadata(t *testing.T) {
	for _, pointer := range []string{"", "/nodes/web"} {
		data, err := json.Marshal(Diagnostic{OriginalPointer: pointer})
		if err != nil {
			t.Fatal(err)
		}
		var fields map[string]json.RawMessage
		if err = json.Unmarshal(data, &fields); err != nil {
			t.Fatal(err)
		}
		if _, present := fields["OriginalPointer"]; present {
			t.Fatal("Go field name changed the diagnostic JSON surface")
		}
		original, present := fields["original_path"]
		if present != (pointer != "") {
			t.Fatalf("original_path presence = %v; want %v", present, pointer != "")
		}
		if present && string(original) != `"/nodes/web"` {
			t.Fatalf("original_path = %s; want authored pointer", original)
		}
	}
}
