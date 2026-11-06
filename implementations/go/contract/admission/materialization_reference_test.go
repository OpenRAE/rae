package admission

import (
	"encoding/json"
	"fmt"
	"slices"
	"testing"
)

type materializationAlgorithmCase struct {
	Kind       string              `json:"kind"`
	Name       string              `json:"name"`
	Document   json.RawMessage     `json:"document"`
	Before     json.RawMessage     `json:"before"`
	After      json.RawMessage     `json:"after"`
	Identities map[string][]string `json:"identities"`
	Path       string              `json:"path"`
	Admitted   bool                `json:"admitted"`
	Canonical  string              `json:"canonical"`
	Namespace  []string            `json:"namespace"`
	Origins    json.RawMessage     `json:"origins"`
}

func TestMaterializationAddressesAndDifferencesMatchPython(t *testing.T) {
	t.Parallel()
	var reference struct {
		Cases []materializationAlgorithmCase `json:"cases"`
	}
	readFullReferenceJSON(t, "testdata/materialization-algorithm-verdicts.json", &reference)
	if len(reference.Cases) != 248 {
		t.Fatal("independent materialization algorithm inventory changed")
	}
	for index, c := range reference.Cases {
		t.Run(fmt.Sprintf("%s/%03d/%s", c.Kind, index, c.Name), func(t *testing.T) {
			switch c.Kind {
			case "address":
				checkMaterializationReferenceAddress(t, c)
			case "difference":
				checkMaterializationReferenceDifference(t, c)
			default:
				t.Fatal("unknown materialization reference owner")
			}
		})
	}
}

func checkMaterializationReferenceAddress(t *testing.T, c materializationAlgorithmCase) {
	t.Helper()
	content := materializationCompiled{full: decodeRuleObject(t, string(c.Document)), identities: c.Identities}
	remaining := 100000
	canonical, namespace, err := materializationSemanticAddress(&content, c.Path, &remaining)
	if (err == nil) != c.Admitted {
		t.Fatalf("semantic address differs from Python (admitted=%v): %v", c.Admitted, err)
	}
	if err == nil && (canonical != c.Canonical || !slices.Equal(namespace, c.Namespace)) {
		t.Fatalf("canonical address=(%s,%v), Python=(%s,%v)", canonical, namespace, c.Canonical, c.Namespace)
	}
}

func checkMaterializationReferenceDifference(t *testing.T, c materializationAlgorithmCase) {
	t.Helper()
	before := decodeRuleObject(t, string(c.Before))
	after := decodeRuleObject(t, string(c.After))
	difference := materializationDiff{identities: c.Identities, remaining: 100000}
	err := difference.walk(materializationOperand{value: before, present: true}, materializationOperand{value: after, present: true})
	if (err == nil) != c.Admitted {
		t.Fatalf("difference result differs from Python (admitted=%v): %v", c.Admitted, err)
	}
	if err != nil {
		return
	}
	got, err := materializationOriginSet(difference.origins)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := materializationOriginSet(array(decodeRuleObject(t, string(c.Origins))))
	if err != nil {
		t.Fatal(err)
	}
	if !equalSet(got, expected) {
		t.Fatalf("origin set differs from Python: got %d origins, expected %d", len(got), len(expected))
	}
}
