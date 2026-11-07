package parity

import (
	"bytes"
	"encoding/json"
	"os"
	"testing"
	"testing/fstest"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type formatOracle struct {
	Name     string `json:"name"`
	Accepted bool   `json:"accepted"`
	Content  string `json:"content"`
}

// CI records exact bytes with the unchanged Python formatter. The ordinary
// corpus stores decoded stdout; this check retains byte-level compatibility.
func TestFormatterBytes(t *testing.T) {
	path := os.Getenv("RAES_FORMAT_BYTE_ORACLE")
	if path == "" {
		t.Skip("CI supplies the independent Python byte oracle")
	}
	rows := loadFormatOracle(t, path)
	byName := formatterCases(t)
	if os.Getenv("CI") == "true" && len(rows) != len(byName) {
		t.Fatal("CI byte oracle does not cover every formatter case")
	}
	if len(rows) == 0 {
		t.Fatal("empty formatter oracle")
	}
	parser, err := authoring.New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	for _, row := range rows {
		if seen[row.Name] {
			t.Fatal("duplicate formatter oracle case")
		}
		seen[row.Name] = true
		t.Run(row.Name, func(t *testing.T) {
			c, present := byName[row.Name]
			if !present {
				t.Fatal("byte oracle has no corpus case")
			}
			checkFormatBytes(t, parser, c, row)
		})
	}
}
func checkFormatBytes(t *testing.T, parser *authoring.Parser, c Case, want formatOracle) {
	t.Helper()
	files := fstest.MapFS{}
	for name, content := range c.Files {
		files[name] = &fstest.MapFile{Data: content}
	}
	command, valid := formatArguments(c.Args)
	if !valid {
		if want.Accepted {
			t.Fatal("oracle accepted invalid command arguments")
		}
		return
	}
	name := command.name
	original := bytes.ReplaceAll(bytes.ReplaceAll(c.Files[name], []byte("\r\n"), []byte("\n")), []byte("\r"), []byte("\n"))
	result, err := parser.Format(authoring.Request{Source: original, Name: name, FS: files})
	if (err == nil) != want.Accepted {
		t.Fatalf("accepted=%v, want %v: %v", err == nil, want.Accepted, err)
	}
	if err == nil {
		if diff := cmp.Diff(want.Content, string(result.Content)); diff != "" {
			t.Errorf("formatter bytes (-want +got):\n%s", diff)
		}
	}
}

func loadFormatOracle(t *testing.T, path string) []formatOracle {
	t.Helper()
	//nolint:gosec // The CI/test command supplies this local oracle path; SDL cannot set it.
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var rows []formatOracle
	if err = json.Unmarshal(raw, &rows); err != nil {
		t.Fatal(err)
	}
	return rows
}
func formatterCases(t *testing.T) map[string]Case {
	t.Helper()
	cases, err := Load(os.DirFS("testdata"))
	if err != nil {
		t.Fatal(err)
	}
	result := map[string]Case{}
	for _, c := range cases {
		if c.Key() == "cli sdl format" {
			result[c.Name] = c
		}
	}
	return result
}
