package admission

import (
	"encoding/json"
	"io/fs"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func preparedEnvelopeFixture(t *testing.T, kind string) binding.RealizationEnvelopeV1 {
	t.Helper()
	raw, err := fs.ReadFile(os.DirFS("testdata/processor"), kind+"-prepared-envelope.json")
	if err != nil {
		t.Fatal(err)
	}
	var envelope binding.RealizationEnvelopeV1
	if json.Unmarshal(raw, &envelope) != nil {
		t.Fatal("envelope fixture")
	}
	return envelope
}
func offerTestValue(t *testing.T, owner *Validator, input any) Fragment { //nolint:ireturn // The native owner issues the value handle under test.
	t.Helper()
	result, err := AdmitFragment(owner, RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		t.Fatal(err)
	}
	return result
}
func TestRealizationOfferUsesTheConfiguredDomain(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	envelope := preparedEnvelopeFixture(t, "exact")
	for _, engine := range []string{"sqlite", "postgresql"} {
		t.Run(engine, func(t *testing.T) {
			actual := offerTestValue(t, owner, engine)
			admitted, err := RealizationOfferAdmits(owner, envelope, "nodes.host.runtime.database_services[0].engine", actual, nil)
			if err != nil || admitted != (engine == "sqlite") {
				t.Fatalf("configured engine admitted=%v err=%v", admitted, err)
			}
		})
	}
}
func TestRealizationOfferRetainsTypedPresenceAndClosedRecords(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	envelope := preparedEnvelopeFixture(t, "closed")
	actual := offerTestValue(t, owner, map[string]any{"engine": "sqlite", "description": ""})
	path := "nodes.host.runtime.database_services[0]"
	for _, typed := range []bool{false, true} {
		t.Run(map[bool]string{false: "raw-extra-field", true: "native-typed-presence"}[typed], func(t *testing.T) {
			var presence map[string][]string
			if typed {
				presence = map[string][]string{"": {"engine"}}
			}
			admitted, err := RealizationOfferAdmits(owner, envelope, path, actual, presence)
			if err != nil || admitted != typed {
				t.Fatalf("typed=%v admitted=%v err=%v", typed, admitted, err)
			}
		})
	}
}

type foreignOfferValue struct{ Fragment }

func (foreignOfferValue) Document() any { panic("foreign fragment called") }
func TestRealizationOfferRefusesForeignInputsAndMalformedTarget(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	envelope := preparedEnvelopeFixture(t, "exact")
	actual := offerTestValue(t, owner, "sqlite")
	if _, err := RealizationOfferAdmits(owner, envelope, "nodes.host", foreignOfferValue{actual}, nil); err == nil {
		t.Fatal("foreign value accepted")
	}
	if _, err := RealizationOfferAdmits(owner, envelope, "nodes..host", actual, nil); err == nil {
		t.Fatal("malformed path accepted")
	}
	if _, err := RealizationOfferAdmits(owner, envelope, strings.Repeat("a", 4097), actual, nil); err == nil {
		t.Fatal("overlong path accepted")
	}
	var empty binding.RealizationEnvelopeV1
	if _, err := RealizationOfferAdmits(owner, empty, "nodes.host", actual, nil); err == nil {
		t.Fatal("malformed envelope accepted")
	}
}
