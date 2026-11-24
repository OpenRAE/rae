package governance

import (
	"strings"
	"testing"
)

type jsonDepthReference struct {
	Kind          string `json:"Kind"`
	Depth         int    `json:"Depth"`
	OrdinaryError bool   `json:"OrdinaryError"`
	StrictError   bool   `json:"StrictError"`
}

func TestJSONReferenceProfiles(t *testing.T) {
	for i, tc := range readReference[[]struct {
		Source        string `json:"Source"`
		OrdinaryError bool   `json:"OrdinaryError"`
		StrictError   bool   `json:"StrictError"`
		Repr          string `json:"Repr"`
	}](t, "json-reference") {
		for _, strict := range []bool{false, true} {
			wantError := tc.OrdinaryError
			if strict {
				wantError = tc.StrictError
			}
			value, err := decodeJSON([]byte(tc.Source), 0, strict)
			if (err != nil) != wantError {
				t.Errorf("case %d, strict=%t: error=%v, want refusal=%t", i, strict, err, wantError)
				continue
			}
			if err != nil {
				continue
			}
			if got := pythonRepr(value); got != tc.Repr {
				t.Errorf("case %d, strict=%t: repr=%s, want %s", i, strict, got, tc.Repr)
			}
		}
	}
}

func TestJSONDepthReference(t *testing.T) {
	for _, tc := range readReference[[]jsonDepthReference](t, "json-depth-reference") {
		source := jsonDepthSource(tc.Kind, tc.Depth)
		for _, strict := range []bool{false, true} {
			wantError := tc.OrdinaryError
			if strict {
				wantError = tc.StrictError
			}
			_, err := decodeJSON(source, 0, strict)
			if (err != nil) != wantError {
				t.Errorf("kind=%s depth=%d strict=%t: error=%v want refusal=%t", tc.Kind, tc.Depth, strict, err, wantError)
			}
		}
	}
}

func jsonDepthSource(kind string, depth int) []byte {
	var source strings.Builder
	object := func(i int) bool { return kind == "object" || kind == "mixed" && i%2 == 0 }
	for i := range depth {
		if object(i) {
			source.WriteString(`{"v":`)
		} else {
			source.WriteByte('[')
		}
	}
	source.WriteByte('0')
	for i := depth - 1; i >= 0; i-- {
		if object(i) {
			source.WriteByte('}')
		} else {
			source.WriteByte(']')
		}
	}
	return []byte(source.String())
}

func TestJSONNativeIngressDepthBound(t *testing.T) {
	for _, kind := range []string{"array", "object", "mixed"} {
		if _, err := decodeJSON(jsonDepthSource(kind, governanceJSONDepth+1), 0, false); err == nil {
			t.Errorf("kind=%s exceeds the existing native ingress bound", kind)
		}
	}
}
