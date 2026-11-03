package admission

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
)

func TestConsumedCatalogsPassTheProductionChecks(t *testing.T) {
	e := boundTestOwner(t)
	if err := e.checkCatalogs(); err != nil {
		t.Fatal(err)
	}
	e.streams["blake3-xof-v1"] = map[string]any{"private-owner-data": "invalid"}
	err := e.checkCatalogs()
	category, ok := fault.CategoryOf(err)
	if !ok || category != fault.Operational || strings.Contains(err.Error(), "private-owner-data") {
		t.Fatalf("catalog refusal=%v", err)
	}
}
