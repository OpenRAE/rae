package admission

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
)

func TestConsumedCatalogsPassTheProductionChecks(t *testing.T) {
	e, err := New()
	if err != nil {
		t.Fatal(err)
	}
	if err = e.checkCatalogs(); err != nil {
		t.Fatal(err)
	}
	documents := e.documents
	if len(documents) != 42 {
		t.Fatalf("len(documents) = %d, want the 42 schema-bound packaged documents", len(documents))
	}
	damaged := append([]concept.Document(nil), documents...)
	for i, document := range damaged {
		if document.ContractID == "random-stream-profile-v1" {
			damaged[i].JSON = []byte(`{"private-owner-data":"invalid"}`)
		}
	}
	err = e.checkDocuments(damaged)
	category, ok := fault.CategoryOf(err)
	if !ok || category != fault.Operational || strings.Contains(err.Error(), "private-owner-data") {
		t.Fatalf("catalog refusal=%v", err)
	}
}
