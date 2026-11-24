package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestBackendManifestNormalizationMatchesReference(t *testing.T) {
	raw, err := os.ReadFile("testdata/processor/backend-manifest-normalization.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string                    `json:"name"`
		Manifest binding.BackendManifestV2 `json:"manifest"`
		Digest   string                    `json:"digest"`
	}
	if decodeErr := json.Unmarshal(raw, &cases); decodeErr != nil {
		t.Fatal(decodeErr)
	}
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			normalized, err := NormalizeBackendManifest(owner, test.Manifest)
			if err != nil {
				t.Fatal(err)
			}

			canonical, err := canonjson.JCS(projectionTestJSON(t, normalized))
			if err != nil {
				t.Fatal(err)
			}
			if got := digest.SHA256(canonical); got != test.Digest {
				t.Fatalf("digest=%s want %s", got, test.Digest)
			}
		})
	}
}
func projectionTestJSON(t *testing.T, input any) []byte {
	t.Helper()
	raw, err := json.Marshal(input)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}
