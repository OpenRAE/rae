package admission

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

type fullReferenceCase struct {
	Name            string `json:"name"`
	InputPath       string `json:"input_path"`
	GoldenSource    string `json:"structural_source"`
	GoldenSurface   string `json:"structural_surface"`
	InputName       string `json:"input_name"`
	Contract        string `json:"contract_id"`
	InputDigest     string `json:"input_sha256"`
	Structural      bool   `json:"structural_admitted"`
	PublishedSchema *bool  `json:"published_schema_admitted"`
	Full            bool   `json:"full_admitted"`
	Owner           string `json:"owner"`
	Check           string `json:"reference_check"`
	Failure         string `json:"failure_class"`
}

// The maintainer chose distinct structural and full reference results. Every
// original fixture still enters the complete production validator. Contextual
// cases use fixed independently supplied owners; payloads cannot mint them.
func TestFullValidationGoldenCorpus(t *testing.T) {
	var recording struct {
		Specification       string              `json:"specification"`
		Cases               []fullReferenceCase `json:"cases"`
		CaseFiles           []string            `json:"case_files"`
		OwnerSources        map[string]string   `json:"owner_sources"`
		FixtureInventory    []string            `json:"fixture_inventory"`
		NoncontractFixtures map[string]string   `json:"noncontract_fixtures"`
	}
	readFullReferenceJSON(t, "testdata/full-admission-verdicts.json", &recording)
	if recording.Specification != "raes-full-admission-parity/v2" {
		t.Fatal("unknown full reference specification")
	}

	if len(recording.Cases) != 0 || len(recording.CaseFiles) != 2 {
		t.Fatal("unexpected reference shard inventory")
	}
	for index, path := range recording.CaseFiles {
		if path != fmt.Sprintf("full-admission-cases-%02d.json", index+1) {
			t.Fatal("unsafe reference shard path")
		}
		var cases []fullReferenceCase
		readFullReferenceJSON(t, "testdata/"+path, &cases)
		if len(cases) != 351 {
			t.Fatal("reference shard inventory changed")
		}
		recording.Cases = append(recording.Cases, cases...)
	}

	checkFullReferenceOwners(t, recording.OwnerSources)
	e := boundTestOwner(t)
	owners := loadFullReferenceOwners(t)
	source, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	checkCompleteFixtureInventory(t, source, recording.Cases, recording.FixtureInventory, recording.NoncontractFixtures)
	for _, c := range recording.Cases {
		t.Run(c.Name, func(t *testing.T) { checkFullReferenceCase(t, e, source, owners, c) })
	}
}
func checkFullReferenceCase(t *testing.T, e *Validator, source fs.FS, owners fullReferenceOwners, c fullReferenceCase) {
	t.Helper()
	path := c.InputPath
	checkRetainedStructuralResult(t, c)
	raw, err := fs.ReadFile(source, path)
	if err != nil {
		t.Fatal(err)
	}
	if digest.SHA256(raw) != c.InputDigest {
		t.Fatal("full reference input differs from original golden bytes")
	}
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if c.PublishedSchema == nil {
		t.Fatal("missing independent schema result")
	}
	if structuralErr := e.low.CheckSchema(c.Contract, raw, limits); (structuralErr == nil) != *c.PublishedSchema {
		t.Fatalf("published schema result differs from Python: %v", structuralErr)
	}
	if (c.GoldenSurface == "schema validate" || c.GoldenSurface == "published-schema reference") && c.Structural != *c.PublishedSchema {
		t.Fatal("original schema result changed")
	}

	context := fullReferenceContext(t, e, owners, c.Owner)
	got, err := e.Validate(c.Contract, raw, limits, context)
	if (err == nil) != c.Full {
		t.Fatalf("full=%v reference=%v owner=%s check=%s failure=%s: %v", err == nil, c.Full, c.Owner, c.Check, c.Failure, err)
	}
	// Authoring factorials have a separate, reference-defined preparation step.
	if err == nil && c.Contract != termExperimentAuthoringInputV1 && !bytes.Equal(got.JSON(), raw) {
		t.Fatal("model comparison changed admitted bytes")
	}
	if err != nil && (got.ContractID() != "" || len(got.JSON()) != 0) {
		t.Fatal("refusal returned admitted data")
	}
}
func readFullReferenceJSON(t *testing.T, path string, value any) {
	t.Helper()
	source := os.DirFS(".")
	if trimmed, ok := strings.CutPrefix(path, "../../parity/"); ok {
		source = os.DirFS("../../parity")
		path = trimmed
	}
	raw, err := fs.ReadFile(source, path)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(raw, value); err != nil {
		t.Fatal(err)
	}
}

func checkFullReferenceOwners(t *testing.T, sources map[string]string) {
	t.Helper()
	if len(sources) != 7 {
		t.Fatal("full reference owners changed")
	}
	for path, expected := range sources {
		if filepath.Base(path) != path {
			t.Fatal("unsafe reference owner path")
		}
		raw, err := fs.ReadFile(os.DirFS("testdata"), path)
		if err != nil {
			t.Fatal(err)
		}
		if digest.SHA256(raw) != expected {
			t.Fatal("reference owner differs from recorded inputs:", path)
		}
	}
}

func checkRetainedStructuralResult(t *testing.T, c fullReferenceCase) {
	t.Helper()
	if c.GoldenSurface == "published-schema reference" {
		if c.GoldenSource != "" {
			t.Fatal("new schema reference misidentified as original golden")
		}
		return
	}
	if !strings.HasPrefix(c.GoldenSource, "cases/") || !fs.ValidPath(c.GoldenSource) {
		t.Fatal("unsafe original result path")
	}
	var record struct {
		Name   string            `json:"name"`
		Files  map[string]string `json:"files"`
		Result struct {
			Valid  *bool `json:"valid"`
			Exit   int   `json:"exit_code"`
			Stdout struct {
				Payload struct {
					Admitted *bool `json:"admitted"`
				} `json:"payload"`
			} `json:"stdout"`
		} `json:"result"`
	}
	readFullReferenceJSON(t, "../../parity/testdata/"+c.GoldenSource, &record)
	original := false
	switch c.GoldenSurface {
	case "schema validate":
		if record.Result.Valid == nil {
			t.Fatal("missing original schema result")
		}
		original = *record.Result.Valid
	case "contract-admission CLI":
		if record.Name != c.Name {
			t.Fatal("original admission identity differs")
		}
		if record.Result.Stdout.Payload.Admitted != nil {
			original = *record.Result.Stdout.Payload.Admitted
		} else if record.Result.Exit == 0 {
			t.Fatal("original successful result lacks admission")
		}
	default:
		t.Fatal("unknown original result surface")
	}
	if c.Structural != original || c.InputDigest != record.Files[c.InputName] {
		t.Fatal("original golden was changed:", c.Name)
	}
}
