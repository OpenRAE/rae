package authoring

import (
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestSemanticExplicitnessCopiesPreserveAdmissionAndIdentity(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	document, err := parser.Decode(Request{Source: []byte("name: intent\nvariables: {v: {type: string, default: operator-private-value}}\nnodes: {host: {type: compute, description: '${v}'}}\n")})
	if err != nil {
		t.Fatal(err)
	}
	if len(document.Explicitness()) != 0 {
		t.Fatal("constructed document has admitted metadata")
	}
	admitted, _, err := parser.Validate(document)
	if err != nil {
		t.Fatal(err)
	}
	before, err := admitted.CanonicalDigest()
	if err != nil {
		t.Fatal(err)
	}
	first := admitted.Explicitness()
	path := "nodes.host.description"
	record := first[path]
	if record.Classification != "constrained" || len(record.Variables) != 1 || record.Variables[0] != "v" {
		t.Fatalf("template record = %+v", record)
	}
	checkIntentValuePrivacy(t, first)
	record.Variables[0] = "changed"
	record.Reason = "changed"
	first[path] = record
	delete(first, "name")
	second := admitted.Explicitness()
	if second[path].Variables[0] != "v" || second[path].Reason != "v: type string" || second["name"].Path != "name" {
		t.Fatal("caller changed retained explicitness metadata")
	}
	after, err := admitted.CanonicalDigest()
	if err != nil || after != before || !admitted.Validated() {
		t.Fatal("metadata copies changed identity or admission")
	}
	if document.Validated() || len(document.Explicitness()) != 0 {
		t.Fatal("admission changed the constructed input")
	}
	var zero *Document
	if len(zero.Explicitness()) != 0 {
		t.Fatal("nil document has metadata")
	}
}

func checkIntentValuePrivacy(t *testing.T, records map[string]ExplicitnessRecord) {
	t.Helper()
	for _, item := range records {
		if strings.Contains(item.Reason, "operator-private-value") {
			t.Fatal("explicitness reason disclosed an authored value")
		}
	}
}
