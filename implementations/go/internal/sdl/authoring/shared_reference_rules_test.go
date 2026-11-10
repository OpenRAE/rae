package authoring

import (
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

func TestSharedReferenceRulesOnConstructedDocuments(t *testing.T) {
	parser := operationParser(t)
	for _, row := range readSemanticVectors(t) {
		if !sharedRuleReferenceCase(row.Name) {
			continue
		}
		t.Run(row.Name, func(t *testing.T) { checkConstructedSharedRules(t, parser, row) })
	}
}

func sharedRuleReferenceCase(name string) bool {
	for _, tag := range []string{"temporal", "dwell", "stateful", "generated", "volume", "service-content"} {
		if strings.Contains(name, tag) {
			return true
		}
	}
	return false
}

func checkSharedReferenceFinding(t *testing.T, finding sdlrules.Finding, expected []semanticFindingVector) {
	t.Helper()
	if !slices.ContainsFunc(expected, func(row semanticFindingVector) bool {
		return row.Message == finding.Message && slices.Equal(row.Owner, []string{finding.Owner.Section, finding.Owner.Name})
	}) {
		t.Fatalf("shared predicate differs from the Python reference: %+v", finding)
	}
}

func checkConstructedSharedRules(t *testing.T, parser *Parser, row semanticVector) {
	t.Helper()
	document, err := parser.Decode(Request{Source: []byte(row.Source)})
	if err != nil {
		t.Fatal(err)
	}
	for _, check := range []func([]byte, map[string][]string) ([]sdlrules.Finding, error){sdlrules.TemporalBindings, sdlrules.StatefulReferences, sdlrules.ServiceMaterialization} {
		findings, err := check(document.modelBytes(), document.semanticOrder())
		if err != nil {
			t.Fatal(err)
		}
		for _, finding := range findings {
			checkSharedReferenceFinding(t, finding, row.Findings)
		}
	}
}
