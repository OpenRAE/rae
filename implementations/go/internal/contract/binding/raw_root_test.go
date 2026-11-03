package binding

import (
	"encoding/json"
	"testing"
)

func TestRawRootTransportsPreserveJSONMethods(t *testing.T) {
	const raw = `{"value":9007199254740993,"nested":[null,false,{"text":"private"}]}`
	for _, id := range []string{"participant-shared-state-record-v1", "participant-control-context-asset-v1", "exploit-path-analysis-evidence-v1"} {
		t.Run(id, func(t *testing.T) {
			transport, err := Decode(id, []byte(raw))
			if err != nil {
				t.Fatal(err)
			}
			encoded, err := json.Marshal(transport)
			if err != nil || string(encoded) != raw {
				t.Fatalf("raw root changed JSON bytes: %v", err)
			}
		})
	}
}
