package processor_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/processor"
)

func TestProcessorManifestUsesPublishedContractAndOrder(t *testing.T) {
	backends := []string{"zeta", "alpha", "zeta"}
	manifest, err := processor.Manifest("1.2.3", backends)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	var value struct {
		Identity struct {
			Name    string `json:"name"`
			Version string `json:"version"`
		} `json:"identity"`
		SupportedContractVersions []string `json:"supported_contract_versions"`
		Compatibility             struct {
			Backends []string `json:"backends"`
		} `json:"compatibility"`
		Capabilities struct {
			SupportedFeatures []string `json:"supported_features"`
		} `json:"capabilities"`
	}

	if err := json.Unmarshal(raw, &value); err != nil {
		t.Fatal(err)
	}
	if value.Identity.Name != "raes-reference-processor" || value.Identity.Version != "1.2.3" || len(value.SupportedContractVersions) != 8 || value.SupportedContractVersions[0] != "processor-manifest-v2" {
		t.Fatalf("manifest identity/contracts = %s", raw)
	}
	if len(value.Compatibility.Backends) != 2 || value.Compatibility.Backends[0] != "alpha" || len(value.Capabilities.SupportedFeatures) != 8 {
		t.Fatalf("manifest capabilities = %s", raw)
	}
	if backends[0] != "zeta" {
		t.Fatal("manifest changed caller backends")
	}
	for _, version := range []string{"", string([]byte{0xff})} {
		if _, err := processor.Manifest(version, nil); err == nil {
			t.Fatal("invalid manifest version accepted")
		}
	}
}

func TestProcessorManifestMatchesPublishedReference(t *testing.T) {
	raw, err := os.ReadFile("../../../contracts/fixtures/processor-manifest/processor-manifest-v2/valid/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var reference struct {
		Identity struct {
			Version string `json:"version"`
		} `json:"identity"`
	}
	if checkErr := json.Unmarshal(raw, &reference); checkErr != nil {
		t.Fatal(checkErr)
	}
	manifest, err := processor.Manifest(reference.Identity.Version, nil)
	if err != nil {
		t.Fatal(err)
	}
	assertReferenceJSON(t, "reference processor declaration", requireJSON(t, manifest), raw)
}
