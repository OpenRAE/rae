package authoring

import (
	"bytes"
	"errors"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestDecodedDocumentOwnsItsBytes(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	input := []byte("name: example\nfeatures: {feature: {type: service}}\n")
	document, err := parser.Decode(Request{Source: input})
	if err != nil {
		t.Fatal(err)
	}
	want := bytes.Clone(document.JSON())
	clear(input)
	changed := document.JSON()
	clear(changed)
	if len(want) == 0 || !bytes.Equal(document.JSON(), want) {
		t.Fatal("caller mutation changed the decoded model")
	}
	if _, err = parser.Decode(Request{Source: []byte("name: again\n")}); err != nil {
		t.Fatalf("another request changed parser state: %v", err)
	}
	if _, err = New(source.Limits{}); err == nil {
		t.Fatal("invalid parser ceilings were accepted")
	}
}

type unreadableImportFS struct{ fstest.MapFS }

func (f unreadableImportFS) Open(name string) (fs.File, error) {
	if name == "broken.yaml" {
		return nil, errors.New("private-payload")
	}
	return f.MapFS.Open(name)
}

func TestDecodeRefusalsPreserveCategoryAndRedactValues(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range []struct {
		name     string
		request  Request
		category fault.Category
	}{
		{"syntax", Request{Source: []byte("name: [\n")}, fault.InvalidInput},
		{"model", Request{Source: []byte("name: example\nnodes: {n: {type: private-payload}}\n")}, fault.InvalidInput},
		{"missing-import", Request{Source: []byte("name: example\nimports: [{source: local:missing.yaml, namespace: m}]\n"), Name: "main.yaml", FS: fstest.MapFS{}}, fault.InvalidInput},
		{"unreadable-import", Request{Source: []byte("name: example\nimports: [{source: local:broken.yaml, namespace: m}]\n"), Name: "main.yaml", FS: unreadableImportFS{fstest.MapFS{}}}, fault.Operational},
		{"workspace", Request{Source: []byte("name: example\nimports: [{source: local:missing.yaml, namespace: m}]\n"), Name: "main.yaml", FS: fstest.MapFS{"raes-trust.yaml": {Data: []byte("value: [private-payload\n")}}}, fault.InvalidInput},
	} {
		t.Run(c.name, func(t *testing.T) {
			_, err := parser.Decode(c.request)
			category, ok := fault.CategoryOf(err)
			if err == nil || !ok || category != c.category || strings.Contains(err.Error(), "private-payload") {
				t.Fatalf("unexpected public refusal: %v (%v)", err, category)
			}
		})
	}
}
