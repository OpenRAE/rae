package parity

import (
	"encoding/json"
	"os"
	"testing"
)

func TestFormatArguments(t *testing.T) {
	cases := []struct {
		name                string
		args                []string
		valid, check, write bool
		source              string
	}{
		{"plain", []string{"sdl", "format", "input.yaml"}, true, false, false, "input.yaml"},
		{"check-before", []string{"sdl", "format", "--check", "input.yaml"}, true, true, false, "input.yaml"},
		{"check-after", []string{"sdl", "format", "input.yaml", "--check"}, true, true, false, "input.yaml"},
		{"write", []string{"sdl", "format", "--write", "input.yaml"}, true, false, true, "input.yaml"},
		{"literal", []string{"sdl", "format", "--", "--check"}, true, false, false, "--check"},
		{"missing", []string{"sdl", "format"}, false, false, false, ""},
		{"exclusive", []string{"sdl", "format", "--check", "--write", "input.yaml"}, false, false, false, ""},
		{"unknown", []string{"sdl", "format", "--unknown", "input.yaml"}, false, false, false, ""},
		{"multiple", []string{"sdl", "format", "one.yaml", "two.yaml"}, false, false, false, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			command, valid := formatArguments(c.args)
			if valid != c.valid {
				t.Fatalf("valid=%v, want %v", valid, c.valid)
			}
			if valid && (command.name != c.source || command.check != c.check || command.write != c.write) {
				t.Errorf("command=%+v", command)
			}
		})
	}
}
func TestFormatCommandNewlinesAndRefusals(t *testing.T) {
	run := formatRunner()
	const accepted = `{"exit_code":0,"stdout":null}`
	const notCanonical = `{"exit_code":1,"stdout":null}`
	const refused = `{"exit_code":2,"stdout":null}`
	cases := []struct {
		name   string
		source []byte
		args   []string
		want   string
	}{
		{"crlf", []byte("name: a\r\n"), []string{"--check", "input.yaml"}, accepted},
		{"cr", []byte("name: a\r"), []string{"input.yaml", "--check"}, accepted},
		{"migration", []byte("Name: a\r\n"), []string{"--check", "input.yaml"}, notCanonical},
		{"utf8", []byte{0xff}, []string{"input.yaml"}, refused},
		{"model", []byte("name: a\nunknown: true\n"), []string{"input.yaml"}, refused},
		{"exclusive", []byte{0xff}, []string{"input.yaml", "--check", "--write"}, refused},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			args := append([]string{"sdl", "format"}, c.args...)
			got, err := run(t.Context(), Case{Args: args, Files: map[string][]byte{"input.yaml": c.source}})
			if err != nil {
				t.Fatal(err)
			}
			diff, err := compareResults([]byte(c.want), got)
			if err != nil {
				t.Fatal(err)
			}
			if diff != "" {
				t.Error(diff)
			}
		})
	}
}

func TestFormatCommandSemanticRefusals(t *testing.T) {
	raw, err := os.ReadFile("../sdl/authoring/testdata/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Cases []struct {
			Name   string `json:"name"`
			Source string `json:"source"`
		} `json:"cases"`
	}
	if err = json.Unmarshal(raw, &fixture); err != nil {
		t.Fatal(err)
	}
	selected := map[string]bool{"materialized-undefined-feature": false, "materialized-stateful-orphan": false, "materialized-behavior-missing-mode": false}
	run := formatRunner()
	for _, row := range fixture.Cases {
		if _, needed := selected[row.Name]; !needed {
			continue
		}
		selected[row.Name] = true
		t.Run(row.Name, func(t *testing.T) { checkFormatSemanticRefusal(t, run, row.Source) })
	}
	for name, found := range selected {
		if !found {
			t.Errorf("missing independent input %s", name)
		}
	}
}

func checkFormatSemanticRefusal(t *testing.T, run Runner, source string) {
	t.Helper()
	got, err := run(t.Context(), Case{Args: []string{"sdl", "format", "input.yaml"}, Files: map[string][]byte{"input.yaml": []byte(source)}})
	if err != nil {
		t.Fatal(err)
	}
	difference, err := compareResults([]byte(`{"exit_code":1,"stdout":null}`), got)
	if err != nil {
		t.Fatal(err)
	}
	if difference != "" {
		t.Error(difference)
	}
}
