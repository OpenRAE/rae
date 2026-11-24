package sdlrules

import (
	"slices"
	"testing"
)

func TestStatefulProjectionRefusesMalformedTypedFields(t *testing.T) {
	for _, raw := range []string{`{`, `[]`, `{"nodes":{"n":{"os":{}}}}`, `{"nodes":{"n":{"runtime":{"environment":[{"value_from":1}]}}}}`} {
		if findings, err := StatefulReferences([]byte(raw), nil); err == nil || len(findings) != 0 {
			t.Errorf("malformed projection produced findings %v, error %v", findings, err)
		}
	}
}

func TestStatefulReferencesKeepsCallerDataAndOrder(t *testing.T) {
	raw := []byte(`{"name":"example","generated_artifacts":{"a":{"generator":"rendered_config","outputs":[{"name":"config","path":"config.txt","sensitivity":"public"}],"provenance":"reference"},"b":{"generator":"rendered_config","outputs":[{"name":"config","path":"config.txt","sensitivity":"public"}],"provenance":"reference"}}}`)
	before := string(raw)
	order := map[string][]string{"/generated_artifacts": {"b", "a"}}
	findings, err := StatefulReferences(raw, order)
	if err != nil || len(findings) != 2 {
		t.Fatalf("findings=%v, error=%v", findings, err)
	}
	if findings[0].Owner.Name != "b" || findings[1].Owner.Name != "a" {
		t.Fatalf("findings did not retain authored order: %v", findings)
	}
	if string(raw) != before || !slices.Equal(order["/generated_artifacts"], []string{"b", "a"}) {
		t.Fatal("reporter changed caller data or field order")
	}
}
