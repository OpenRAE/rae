package admission

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestParticipantFeatureSupportUsesStrengthAndExistingContractCatalog(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	record := fixtureObject(t, "fixtures/backend-manifest/backend-manifest-v2/valid/feature-support-bounded.json")
	raw, err := json.Marshal(record)
	if err != nil {
		t.Fatal(err)
	}
	var manifest binding.BackendManifestV2
	if json.Unmarshal(raw, &manifest) != nil {
		t.Fatal("fixture decode")
	}
	capability := object(at(record, "capabilities", "participant_runtime"))
	var feature string
	for _, declaration := range array(capability["feature_support"]) {
		if stringAt(declaration, "support_level") == "bounded" {
			feature = stringAt(declaration, "feature")
			break
		}
	}
	if feature == "" {
		t.Fatal("fixture lacks bounded feature")
	}
	gaps, err := ParticipantFeatureSupportGaps(owner, manifest, []string{feature, feature}, "exact")
	if err != nil {
		t.Fatal(err)
	}
	if len(gaps) != 1 || !strings.Contains(gaps[0], "requires exact support") {
		t.Fatalf("gaps=%v", gaps)
	}
	gaps, err = ParticipantFeatureSupportGaps(owner, manifest, []string{feature}, "bounded")
	if err != nil || len(gaps) != 0 {
		t.Fatalf("bounded=%v,%v", gaps, err)
	}
	if _, err := ParticipantFeatureSupportGaps(owner, manifest, []string{feature}, "invented"); err == nil {
		t.Fatal("unknown strength accepted")
	}
}
