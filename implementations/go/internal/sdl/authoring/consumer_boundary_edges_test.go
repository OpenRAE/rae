package authoring

import (
	"encoding/json"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestNativeConsumerFacadesRefuseDocumentsWithoutAdmission(t *testing.T) {
	p := operationParser(t)
	for _, document := range []*Document{nil, {}, operationDocument(t, p, "name: raw\n")} {
		if _, err := document.ConceptSubjects(); err == nil {
			t.Fatal("unadmitted document supplied concept subjects")
		}
		if _, err := document.ArtifactSources(); err == nil {
			t.Fatal("unadmitted document supplied artifact sources")
		}
		if _, err := document.ObservationScopes(nil, nil, nil); err == nil {
			t.Fatal("unadmitted document supplied observation scopes")
		}
		if _, _, err := p.envelopeMembershipView(document); err == nil {
			t.Fatal("uninstantiated document supplied envelope membership")
		}
	}
	if _, err := p.ComparisonProjection(nil, "1"); err == nil {
		t.Fatal("missing comparison source accepted")
	}
	if _, err := p.ComparisonProjection(operationDocument(t, p, "name: raw\n"), "3"); err == nil {
		t.Fatal("unknown comparison profile accepted")
	}
	if _, err := p.EnvelopeMembershipDiagnostics(nil, binding.RealizationEnvelopeV1{}); err == nil {
		t.Fatal("missing membership source accepted")
	}
}

func TestInstantiatedExplicitnessKeepsParameterNamesAndCopies(t *testing.T) {
	p := operationParser(t)
	document := operationDocument(t, p, "name: concrete-intent\nvariables: {family: {type: string, default: linux}}\nnodes: {host: {type: compute, os: '${family}'}}\n")
	instance, err := p.Instantiate(document, nil, "")
	if err != nil {
		t.Fatal(err)
	}
	records := instance.Explicitness()
	record := records["nodes.host.os"]
	if record.Classification != "constrained" || len(record.Variables) != 1 || record.Variables[0] != "family" {
		t.Fatalf("concrete provenance lost authored parameter: %+v", record)
	}
	record.Variables[0] = "changed"
	delete(records, "nodes.host.os")
	if instance.Explicitness()["nodes.host.os"].Variables[0] != "family" {
		t.Fatal("caller changed admitted instantiation provenance")
	}
}

func TestFiniteSelectionPopulationRejectsUnboundedAndMismatchedEnumeration(t *testing.T) {
	for _, test := range []struct {
		kind, domain string
		population   int
		finite       bool
	}{
		{"parameter", `{"kind":"enum","values":[1,2]}`, 2, true},
		{"parameter", `{"kind":"numeric-interval","numeric_type":"integer","lower":2,"upper":4}`, 3, true},
		{"parameter", `{"kind":"numeric-interval","numeric_type":"integer","lower":0,"upper":1000001}`, 0, false},
		{"parameter", `{"kind":"numeric-interval","numeric_type":"number","lower":0,"upper":1}`, 0, false},
		{"governed-reference", `{"allowed_refs":["a","b"]}`, 2, true},
	} {
		t.Run(test.kind+test.domain, func(t *testing.T) {
			point := semanticVariation{Kind: test.kind}
			if err := json.Unmarshal([]byte(test.domain), &point.Domain); err != nil {
				t.Fatal(err)
			}
			population, finite := variationPopulation(point)
			if population != test.population || finite != test.finite {
				t.Fatalf("population=%d/%t, want %d/%t", population, finite, test.population, test.finite)
			}
		})
	}
	point := semanticVariation{Kind: variationAlternativeKind, Alternatives: map[string]semanticVariationMember{"a": {}, "b": {}}}
	points := map[string]semanticVariation{"choice": point}
	for _, raw := range []string{`[]`, `{"kind":"invented","point_ref":"choice"}`, `{"kind":"enumerate","point_ref":"missing","output_bound":2}`, `{"kind":"enumerate","point_ref":"choice","output_bound":1}`} {
		if selectionPolicyAdmitted(json.RawMessage(raw), points) {
			t.Fatalf("invalid enumeration admitted: %s", raw)
		}
	}
	if !selectionPolicyAdmitted(json.RawMessage(`{"kind":"enumerate","point_ref":"choice","output_bound":2}`), points) {
		t.Fatal("complete finite enumeration refused")
	}
}
