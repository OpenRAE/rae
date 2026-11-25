package authoring

import (
	"encoding/json"
	"io/fs"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const nativeOwnerTest = "implementations/go/internal/sdl/authoring TestNativeOwnerContractFixtures"

type nativeOwnerReference struct {
	Contract        string `json:"contract_id"`
	InputDigest     string `json:"input_sha256"`
	PublishedSchema bool   `json:"published_schema_admitted"`
	Full            bool   `json:"full_admitted"`
	CoveredBy       string `json:"covered_by"`
}

// The contract admission reference records the Python verdict. This package
// owns the native SDL phase callback, so it checks the complete Go result.
func TestNativeOwnerContractFixtures(t *testing.T) {
	references := readNativeOwnerReferences(t)
	packaged, err := corpus.Open()
	if err != nil {
		t.Fatal(err)
	}
	schemas, err := validation.New(nil)
	if err != nil {
		t.Fatal(err)
	}
	owner, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	validate := func(id string, data []byte, limits ingress.Limits) (validation.Value, error) {
		return owner.Validate(id, data, limits, parser)
	}
	for path, reference := range references {
		t.Run(path, func(t *testing.T) { checkNativeOwnerFixture(t, packaged, schemas, validate, path, reference) })
	}
}

func readNativeOwnerReferences(t *testing.T) map[string]nativeOwnerReference {
	t.Helper()
	var recording struct {
		Native map[string]nativeOwnerReference `json:"native_owner_fixtures"`
	}
	raw, err := os.ReadFile("../../../contract/admission/testdata/full-admission-verdicts.json")
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &recording); err != nil {
		t.Fatal(err)
	}
	owned := map[string]nativeOwnerReference{}
	for path, reference := range recording.Native {
		if reference.CoveredBy == nativeOwnerTest {
			owned[path] = reference
		}
	}
	if len(owned) != 1 {
		t.Fatal("native owner fixture inventory changed")
	}
	return owned
}

func checkNativeOwnerFixture(t *testing.T, packaged fs.FS, schemas *validation.Validator, validate func(string, []byte, ingress.Limits) (validation.Value, error), path string, reference nativeOwnerReference) {
	t.Helper()
	data, err := fs.ReadFile(packaged, path)
	if err != nil {
		t.Fatal(err)
	}
	if digest.SHA256(data) != reference.InputDigest {
		t.Fatal("fixture differs from the recorded Python input")
	}
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if err = schemas.CheckSchema(reference.Contract, data, limits); (err == nil) != reference.PublishedSchema {
		t.Fatalf("published schema result differs from Python: %v", err)
	}
	got, err := validate(reference.Contract, data, limits)
	if (err == nil) != reference.Full {
		t.Fatalf("full=%v reference=%v: %v", err == nil, reference.Full, err)
	}
	if err == nil && string(got.JSON()) != string(data) {
		t.Fatal("admission changed the fixture bytes")
	}
}

func TestSDLPhaseOwnerChecksTheRequestedPhase(t *testing.T) {
	parser, err := New(source.DefaultLimits())
	if err != nil {
		t.Fatal(err)
	}
	authored := []byte("name: phase\nnodes:\n  host: {type: compute}\n")
	got, err := parser.AdmitSDLPhase(admission.SDLPhaseRequest{ContractID: authoringContract, Source: authored})
	if err != nil || got.ContractID != authoringContract || got.SourceSHA256 != digest.SHA256(authored) {
		t.Fatalf("got %v, %v, want the authoring phase admitted", got, err)
	}
	if _, err = parser.AdmitSDLPhase(admission.SDLPhaseRequest{ContractID: materializedContract, Source: authored}); err == nil {
		t.Fatal("got nil error, want an authoring source refused as a materialized phase")
	}
	for name, raw := range map[string]string{
		"wrong profile":    `{"profile":"raes-sdl-instantiated-snapshot/v2","scenario":{}}`,
		"extra member":     `{"profile":"raes-sdl-instantiated-snapshot/v3","scenario":{},"x":1}`,
		"not instantiated": `{"profile":"raes-sdl-instantiated-snapshot/v3","scenario":{"name":"plain"}}`,
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := parser.AdmitSDLPhase(admission.SDLPhaseRequest{ContractID: "instantiated-scenario-snapshot-v2", Source: []byte(raw)}); err == nil {
				t.Fatal("got nil error, want the snapshot refused")
			}
		})
	}
}

func TestProvenancePointersUseCanonicalArrayIndexes(t *testing.T) {
	root := map[string]any{"items": []any{"a", "b"}}
	for pointer, expected := range map[string]bool{"/items/1": true, "/items/01": false, "/items/-1": false, "/items/x": false, "/items/2": false, "/items/0/x": false, "/missing": false} {
		if _, got := provenancePointer(root, pointer); got != expected {
			t.Fatalf("pointer %q: got %v, want %v", pointer, got, expected)
		}
	}
}
