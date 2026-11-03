package admission

import (
	"slices"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// TestCompleteRegistry is the CI guard for the expanded scope. It enumerates
// missing implementations independently of fixtures and never inserts stubs.
func TestCompleteRegistry(t *testing.T) {
	e, err := newCatalogOwner()
	if err != nil {
		t.Fatal(err)
	}
	base, err := validation.New(nil)
	if err != nil {
		t.Fatal(err)
	}
	missing := map[string]bool{}
	for _, key := range base.Keys() {
		if _, ok := e.checker(key.InvariantID); !ok {
			missing[key.InvariantID] = true
		}
	}
	ids := make([]string, 0, len(missing))
	for id := range missing {
		ids = append(ids, id)
	}
	slices.Sort(ids)
	for _, id := range ids {
		t.Errorf("missing contract rule %s", id)
	}
	if len(ids) > 0 {
		return
	}
	if _, err := New(); err != nil {
		t.Fatal(err)
	}
}

func TestCatalogIngressFailsClosed(t *testing.T) {
	for _, raw := range []string{`{"v":1,"v":2}`, `{"v":NaN}`, `[]`, `{"private-payload":`, strings.Repeat(" ", 8*1048576+1)} {
		_, err := readCatalog(fstest.MapFS{"catalog.json": {Data: []byte(raw)}}, "catalog.json")
		if err == nil || strings.Contains(err.Error(), "private-payload") {
			t.Errorf("readCatalog failure = %v, want safe refusal", err)
		}
	}
}
