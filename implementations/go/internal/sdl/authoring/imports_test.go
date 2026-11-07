package authoring

import (
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type forbiddenFS struct{}

func (forbiddenFS) Open(string) (fs.File, error) { panic("supplied imports consulted the filesystem") }

type importVector struct {
	Limits   json.RawMessage   `json:"limits"`
	Code     string            `json:"code"`
	Name     string            `json:"name"`
	Content  string            `json:"content"`
	Files    map[string]string `json:"files"`
	Accepted bool              `json:"accepted"`
	Supplied bool              `json:"supplied"`
}

func TestImportReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/imports.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []importVector
	if err = json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) { checkImportVector(t, parser, c) })
	}
}
func checkImportVector(t *testing.T, parser *Parser, c importVector) {
	t.Helper()
	if len(c.Limits) > 0 {
		limits := source.DefaultLimits()
		if err := json.Unmarshal(c.Limits, &limits); err != nil {
			t.Fatal(err)
		}
		configured, err := New(limits)
		if err != nil {
			t.Fatal(err)
		}
		parser = configured
	}
	result, err := parser.Format(importRequest(c))
	if (err == nil) != c.Accepted {
		t.Fatalf("accepted=%v, want %v: %v", err == nil, c.Accepted, err)
	}
	if c.Code != "" {
		classified, ok := errors.AsType[interface {
			error
			Code() string
		}](err)
		if !ok || classified.Code() != c.Code {
			t.Errorf("refusal code: %v, want %s", err, c.Code)
		}
	}
	if err == nil {
		if diff := cmp.Diff(c.Content, string(result.Content)); diff != "" {
			t.Errorf("content (-want +got):\n%s", diff)
		}
	}
}
func importRequest(c importVector) Request {
	request := Request{Source: []byte(c.Files["main.yaml"]), Name: "main.yaml"}
	if c.Supplied {
		request.Sources = map[string][]byte{}
		for name, content := range c.Files {
			request.Sources[name] = []byte(content)
		}
		request.FS = forbiddenFS{}
		return request
	}
	files := fstest.MapFS{}
	for name, content := range c.Files {
		files[name] = &fstest.MapFile{Data: []byte(content)}
	}
	request.FS = files
	return request
}
