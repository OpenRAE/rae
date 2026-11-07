package packaged

import (
	"errors"
	"io/fs"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

func TestReadChecksEachDocument(t *testing.T) {
	schemas, err := validation.New(nil)
	if err != nil {
		t.Fatalf("validation.New() error = %v", err)
	}
	packagedCorpus, err := corpus.Open()
	if err != nil {
		t.Fatalf("corpus.Open() error = %v", err)
	}
	data, err := fs.ReadFile(packagedCorpus, "concept-authority/concept-families-v1.json")
	if err != nil {
		t.Fatalf("ReadFile() error = %v", err)
	}
	families := string(data)
	source := fstest.MapFS{
		"ok.json":        {Data: []byte(families)},
		"plain.json":     {Data: []byte(`{"a":1}`)},
		"schema.json":    {Data: []byte(`{"schema_version":"concept-families/v1"}`)},
		"duplicate.json": {Data: []byte(`{"a":1,"a":2}`)},
		"array.json":     {Data: []byte(`[1]`)},
		"large.json":     {Data: []byte(`{"a":"` + strings.Repeat("x", MaxBytes) + `"}`)},
		"deep.json":      {Data: []byte(strings.Repeat(`{"a":`, MaxDepth+1) + "1" + strings.Repeat("}", MaxDepth+1))},
	}
	got, err := Read(source, schemas, []File{{ContractID: "concept-families-v1", Path: "ok.json"}, {Path: "plain.json"}})
	if err != nil || len(got) != 2 || string(got[0]) != families || string(got[1]) != `{"a":1}` {
		t.Fatalf("Read(valid) = %q, %v; want both documents", got, err)
	}
	for name, file := range map[string]File{
		"missing":   {Path: "missing.json"},
		"schema":    {ContractID: "concept-families-v1", Path: "schema.json"},
		"duplicate": {Path: "duplicate.json"},
		"array":     {Path: "array.json"},
		"large":     {Path: "large.json"},
		"deep":      {Path: "deep.json"},
	} {
		if _, err := Read(source, schemas, []File{file}); !errors.Is(err, ErrDocument) {
			t.Errorf("Read(%s) error = %v, want ErrDocument", name, err)
		}
	}
	exact := fstest.MapFS{"exact.json": {Data: []byte(`{"a":"` + strings.Repeat("x", MaxBytes-8) + `"}`)}}
	if _, err := Read(exact, schemas, []File{{Path: "exact.json"}}); err != nil {
		t.Errorf("Read(exactly MaxBytes) error = %v, want nil", err)
	}
}
