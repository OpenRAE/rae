package authoring

import (
	"encoding/json"
	"os"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type semanticCorpusVector struct {
	semanticVector

	Constructed bool `json:"constructed"`
	Migration   bool `json:"accept_migration"`
}

// CI records every retained MCP source input with the unchanged reference.
// These checks exercise the SDL owner independently of the response envelope.
func TestSemanticCorpusReference(t *testing.T) {
	path := os.Getenv("RAES_SEMANTIC_ORACLE")
	if path == "" {
		t.Skip("CI supplies the independent semantic corpus oracle")
	}
	//nolint:gosec // The test command supplies this local path; SDL cannot set it.
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var oracle struct {
		Schema   string                 `json:"schema"`
		Complete bool                   `json:"complete"`
		Cases    []semanticCorpusVector `json:"cases"`
	}
	if err = json.Unmarshal(raw, &oracle); err != nil {
		t.Fatal(err)
	}
	if oracle.Schema != "raes-sdl-semantic-oracle/v1" || len(oracle.Cases) == 0 || os.Getenv("CI") == "true" && !oracle.Complete {
		t.Fatal("missing or incomplete semantic corpus oracle")
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, row := range oracle.Cases {
		if seen[row.Name] {
			t.Fatal("duplicate semantic corpus case")
		}
		seen[row.Name] = true
		t.Run(row.Name, func(t *testing.T) { checkSemanticCorpusVector(t, parser, row) })
	}
}

func checkSemanticCorpusVector(t *testing.T, parser *Parser, row semanticCorpusVector) {
	t.Helper()
	policy := "reject"
	if row.Migration {
		policy = "accept"
	}
	request := Request{Source: []byte(row.Source), Name: "main.yaml", FS: fstest.MapFS{}}
	document, err := parser.decode(request.Source, request.Name, policy)
	if err == nil {
		err = parser.checkImports(document, request, nil)
	}
	if (err == nil) != row.Constructed {
		t.Fatalf("construction = %v; want constructed %v", err, row.Constructed)
	}
	if err == nil {
		checkConstructedSemanticVector(t, parser, document, row.semanticVector)
	}
}
