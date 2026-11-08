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

	Source      json.RawMessage `json:"source"`
	Constructed bool            `json:"constructed"`
	Migration   json.RawMessage `json:"accept_migration"`
	InputError  string          `json:"input_error"`
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
	if len(row.Source) == 0 || row.Source[0] != '"' {
		if row.InputError != "non-text-source" || row.Constructed {
			t.Fatal("non-text source must retain its transport refusal")
		}
		return
	}
	if row.InputError != "" {
		t.Fatal("text source must reach the SDL owner")
	}
	if err := json.Unmarshal(row.Source, &row.semanticVector.Source); err != nil {
		t.Fatal(err)
	}
	var migration bool
	if err := json.Unmarshal(row.Migration, &migration); err != nil {
		t.Fatal(err)
	}
	policy := "reject"
	if migration {
		policy = "accept"
	}
	request := Request{Source: []byte(row.semanticVector.Source), Name: "main.yaml", FS: fstest.MapFS{}}
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
