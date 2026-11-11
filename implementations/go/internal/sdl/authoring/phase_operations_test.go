package authoring

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestConcretePhaseAdmissionPreservesSuppliedFields(t *testing.T) {
	parser := operationParser(t)
	input := operationDocument(t, parser, "name: concrete\n")
	concrete, err := parser.Instantiate(input, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]json.RawMessage
	if err = json.Unmarshal(concrete.JSON(), &fields); err != nil {
		t.Fatal(err)
	}
	sparse, err := json.Marshal(map[string]json.RawMessage{"name": fields["name"], "instantiation_provenance": fields["instantiation_provenance"]})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = parser.AdmitInstantiated(sparse); err != nil {
		t.Fatalf("sparse concrete owner admission: %v", err)
	}
	if _, err = parser.models.Validate(instantiatedContract, sparse, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}, parser); err != nil {
		t.Fatalf("independent contract admission changed supplied fields: %v", err)
	}
}

func TestFamilyAdmissionOwnsPhaseAndReadsNoAmbientSources(t *testing.T) {
	parser := operationParser(t)
	original := operationDocument(t, parser, "name: family\n")
	before := original.JSON()
	family, err := parser.AdmitFamily(original)
	if err != nil {
		t.Fatal(err)
	}
	if !family.Validated() || family == original || !bytes.Equal(before, original.JSON()) {
		t.Fatal("family admission changed its source or retained mutable ownership")
	}
	copyOfFamily := family.JSON()
	clear(copyOfFamily)
	if _, err = parser.Select(family, []byte(`{}`), nil); err != nil {
		t.Fatalf("family byte mutation changed sealed state: %v", err)
	}
	concrete, err := parser.Instantiate(original, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	for _, document := range []*Document{nil, {}, concrete} {
		if admitted, err := parser.AdmitFamily(document); err == nil || admitted != nil {
			t.Fatal("foreign phase acquired family authority")
		}
	}
	for _, source := range []string{
		`{"name":"forged","nodes":{"lib.__private.host":{"type":"compute"}},"instantiation_provenance":{}}`,
		`{"name":"forged","nodes":{"lib.__private.host":{"type":"compute"}},"expansion_provenance":{}}`,
		`{"name":"forged","agents":{"a":{"actions":["lib.__private.action"]}}}`,
	} {
		if admitted, err := parser.Decode(Request{Source: []byte(source)}); err == nil || admitted != nil {
			t.Fatal("authored state acquired private expanded privileges")
		}
	}
}
