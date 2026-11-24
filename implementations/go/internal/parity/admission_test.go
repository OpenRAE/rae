package parity

import (
	"encoding/json"
	"io/fs"
	"maps"
	"os"
	"slices"
	"strings"
	"testing"
)

type admissionCaseInventory struct {
	Specification string   `json:"specification"`
	Cases         []string `json:"cases"`
}

func TestPortableContractAdmissionCorpus(t *testing.T) {
	cases := recordedAdmissionCases(t)
	run := portableAdmissionRunner()
	for _, name := range slices.Sorted(maps.Keys(cases)) {
		t.Run(name, func(t *testing.T) {
			checkPortableAdmissionCase(t, run, cases[name])
		})
	}
}
func recordedAdmissionCases(t *testing.T) map[string]Case {
	t.Helper()

	source := os.DirFS("testdata")
	if err := validateManifest(source); err != nil {
		t.Fatal(err)
	}
	inventory := admissionCaseInventory{}
	if err := decodeFile(os.DirFS("."), "admission-inventory.json", &inventory); err != nil {
		t.Fatal(err)
	}
	if inventory.Specification != "raes-portable-admission-parity/v1" {
		t.Fatal("unknown admission inventory")
	}
	cases := portableAdmissionCases(t, source)
	if !slices.Equal(inventory.Cases, slices.Sorted(maps.Keys(cases))) {
		t.Fatal("portable admission fixture inventory changed")
	}
	return cases
}

func portableAdmissionCases(t *testing.T, source fs.FS) map[string]Case {
	t.Helper()
	const directory = "cases/cli/semantic-validate"
	entries, err := fs.ReadDir(source, directory)
	if err != nil {
		t.Fatal(err)
	}
	cases := map[string]Case{}
	for _, entry := range entries {
		c, err := loadCase(source, directory+"/"+entry.Name())
		if err != nil {
			t.Fatal(err)
		}
		if !strings.HasPrefix(c.Name, "contracts/fixtures/") || portableAdmissionID(c.Args) == "sdl-yaml/v1" {
			continue
		}
		if portableAdmissionID(c.Args) == "" || c.Files["input.json"] == nil {
			t.Fatal("portable fixture has no contract or input")
		}
		if _, present := cases[c.Name]; present {
			t.Fatal("duplicate portable admission fixture")
		}
		cases[c.Name] = c
	}
	return cases
}
func portableAdmissionID(args []string) string {
	for index, arg := range args {
		if arg == "--contract" && index+1 < len(args) {
			return args[index+1]
		}
	}
	return ""
}

func checkPortableAdmissionCase(t *testing.T, run Runner, c Case) {
	t.Helper()

	expected := portableRecordedAdmission(t, c)
	c.Args = []string{portableAdmissionID(c.Args)}
	c.Files = map[string][]byte{"payload.json": c.Files["input.json"]}
	got, err := run(t.Context(), c)
	if err != nil {
		t.Fatal(err)
	}
	var actual struct {
		Admitted bool `json:"admitted"`
	}
	if err = json.Unmarshal(got, &actual); err != nil {
		t.Fatal(err)
	}
	if actual.Admitted != expected {
		t.Fatalf("admitted=%v, reference=%v", actual.Admitted, expected)
	}
}

func portableRecordedAdmission(t *testing.T, c Case) bool {
	t.Helper()

	var recorded struct {
		ExitCode *int `json:"exit_code"`
		Stdout   struct {
			Payload struct {
				Admitted *bool `json:"admitted"`
			} `json:"payload"`
		} `json:"stdout"`
	}
	if err := json.Unmarshal(c.Result, &recorded); err != nil || recorded.ExitCode == nil {
		t.Fatal("missing recorded admission")
	}
	if recorded.Stdout.Payload.Admitted == nil {
		if *recorded.ExitCode != 0 {
			return false
		}
		t.Fatal("successful result has no admission")
	}
	return *recorded.Stdout.Payload.Admitted
}
