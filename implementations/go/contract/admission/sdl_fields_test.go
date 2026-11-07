package admission

import (
	"strings"
	"testing"
)

func TestSDLFieldRecordsFailClosed(t *testing.T) {
	for _, raw := range []string{`{}`, `null`, `{"X":{}}`, `{"X":{"id":"unknown"}}`, `{"":{"id":"portable"}}`, `{"X":{"":"portable"}}`, `{"X":{"id":"nullable-unknown"}}`, `{"X":{"id":"list-"}}`, `{"X":{"id":"` + strings.Repeat("list-", 17) + `portable"}}`} {
		if _, err := decodeSDLFieldRules(raw); err == nil {
			t.Errorf("accepted invalid record shape: %s", raw)
		}
	}
	if _, err := readSDLFieldRules(); err != nil {
		t.Fatal(err)
	}
}
