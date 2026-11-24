package authoring

import (
	"bytes"
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestSnapshotPhaseAdmissionBindsExactBytesAndRejectsOtherEnvelopes(t *testing.T) {
	p := operationParser(t)
	d := operationDocument(t, p, "name: snapshot\n")
	instance, err := p.Instantiate(d, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	raw, err := instance.Snapshot()
	if err != nil {
		t.Fatal(err)
	}
	got, err := p.AdmitSDLPhase(admission.SDLPhaseRequest{ContractID: snapshotContract, Source: raw})
	if err != nil || got.ContractID != snapshotContract || got.SourceSHA256 != digest.SHA256(raw) || !bytes.Equal(got.Document, raw) {
		t.Fatalf("snapshot phase binding changed: %+v %v", got, err)
	}
	got.Document[0] = 'x'
	if raw[0] != '{' {
		t.Fatal("phase admission returned caller-owned bytes")
	}
	for _, bad := range []string{`{`, `[]`, `{"profile":"future","scenario":{}}`, `{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{},"extra":true}`, `{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{"name":"missing-provenance"}}`} {
		if _, err := p.AdmitSDLPhase(admission.SDLPhaseRequest{ContractID: snapshotContract, Source: []byte(bad)}); err == nil {
			t.Fatalf("invalid snapshot admitted: %s", bad)
		}
	}
	if _, err := p.AdmitSDLPhase(admission.SDLPhaseRequest{ContractID: "future", Source: raw}); err == nil {
		t.Fatal("unknown source phase admitted")
	}
}

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
