package authoring

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestSemanticImportReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/semantic-imports.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		semanticVector

		Files    map[string]string `json:"files"`
		Supplied bool              `json:"supplied"`
	}
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range cases {
		t.Run(row.Name, func(t *testing.T) {
			request := importRequest(importVector{Files: row.Files, Supplied: row.Supplied})
			document, err := parser.Decode(request)
			if err != nil {
				t.Fatal(err)
			}
			original := document.JSON()
			mutateImportRequest(request)
			checkConstructedSemanticVector(t, parser, document, row.semanticVector)
			if document.Validated() || !bytes.Equal(original, document.JSON()) {
				t.Fatal("semantic admission changed the constructed authored view")
			}
		})
	}
}

func mutateImportRequest(request Request) {
	for i := range request.Source {
		request.Source[i] = 'x'
	}
	for _, sourceBytes := range request.Sources {
		for i := range sourceBytes {
			sourceBytes[i] = 'x'
		}
	}
}
