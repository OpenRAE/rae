package stub_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/backend/stub"
	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
)

func TestManifestOptionsMatchPythonReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/manifest-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []manifestReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 64 {
		t.Fatal("reference corpus")
	}
	for _, c := range cases {
		checkManifestReference(t, c)
	}
	defaults := stub.DefaultOptions()
	if !defaults.WithOrchestrator || !defaults.WithEvaluator || !defaults.WithParticipantRuntime || !defaults.WithObservation || defaults.WithTime || defaults.WithRealizationEnvelope {
		t.Fatal("incorrect defaults")
	}
}

type manifestReference struct {
	Options [6]bool `json:"options"`
	SHA256  string  `json:"sha256"`
	Error   bool    `json:"error"`
}

func checkManifestReference(t *testing.T, c manifestReference) {
	t.Helper()
	options := stub.Options{WithOrchestrator: c.Options[0], WithEvaluator: c.Options[1], WithParticipantRuntime: c.Options[2], WithTime: c.Options[3], WithObservation: c.Options[4], WithRealizationEnvelope: c.Options[5]}
	manifest, err := stub.Manifest(options)
	if c.Error {
		if err == nil {
			t.Fatalf("reference refuses %+v", options)
		}
		return
	}
	if err != nil {
		t.Fatalf("%+v: %v", options, err)
	}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	canonical, err := canonjson.Sorted(raw, true)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(canonical)
	if hex.EncodeToString(sum[:]) != c.SHA256 {
		t.Fatalf("manifest differs for %+v: %s", options, canonical)
	}
}
