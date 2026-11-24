package admission

import (
	"encoding/json"
	"os"
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type augmentationExpectedDiagnostic struct {
	Code    string `json:"code"`
	Domain  string `json:"domain"`
	Address string `json:"address"`
	Message string `json:"message"`
}
type augmentationReferenceCase struct {
	Name        string                             `json:"name"`
	Report      binding.BackendAugmentationScopeV1 `json:"report"`
	Request     json.RawMessage                    `json:"request"`
	Manifest    binding.BackendManifestV2          `json:"manifest"`
	Previous    binding.RuntimeSnapshotV1          `json:"previous"`
	Original    materializationPhaseFixture        `json:"original"`
	Prospective materializationPhaseFixture        `json:"prospective"`
	Error       bool                               `json:"error"`
	Diagnostics []augmentationExpectedDiagnostic   `json:"diagnostics"`
}

func TestAugmentationPreparationMatchesIndependentPureReference(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	var cases []augmentationReferenceCase
	for _, path := range []string{"testdata/processor/augmentation-preparation.json", "testdata/processor/augmentation-preparation-2.json"} {
		raw, err := os.ReadFile(path) //nolint:gosec // The fixture paths are a fixed literal list.
		if err != nil {
			t.Fatal(err)
		}
		var part []augmentationReferenceCase
		if err := json.Unmarshal(raw, &part); err != nil {
			t.Fatal(err)
		}
		cases = append(cases, part...)
	}
	if len(cases) != 15 {
		t.Fatal("augmentation reference fixture")
	}
	for _, c := range cases {
		t.Run(c.Name, func(t *testing.T) {
			checkAugmentationReference(t, owner, c)
		})
	}
}

func checkAugmentationReference(t *testing.T, owner *Validator, c augmentationReferenceCase) {
	t.Helper()
	request, err := owner.Validate("provisioning-plan-v1", c.Request, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal(err)
	}
	findings, err := CheckAugmentationPreparation(owner, c.Report, request, c.Manifest, c.Previous, c.Original.compilation(), c.Prospective.compilation())
	if (err != nil) != c.Error {
		t.Fatalf("native error=%v reference refused=%v", err, c.Error)
	}
	if len(findings) != len(c.Diagnostics) {
		t.Fatalf("native diagnostics=%+v reference=%+v", findings, c.Diagnostics)
	}
	for i, expected := range c.Diagnostics {
		finding := findings[i]
		actual := augmentationExpectedDiagnostic{finding.Code, finding.Domain, finding.Address, finding.Message}
		if actual != expected {
			t.Fatalf("native diagnostic=%+v reference=%+v", actual, expected)
		}
	}
}

func TestAugmentationReportBoundsScopeResolutionBeforeEncoding(t *testing.T) {
	effects := make([]any, 4096)
	for i := range effects {
		effects[i] = map[string]any{"field_pointer": "/nodes/host/runtime/" + strconv.Itoa(i), "requirement_refs": []string{"backend-operational"}, "affected_scopes": []string{"/nodes/host", "/nodes/host/runtime"}}
	}
	var report binding.BackendAugmentationScopeV1
	requireNoError(t, json.Unmarshal(requireJSON(t, map[string]any{"content": "{}", "effects": effects}), &report))
	requireNoError(t, augmentationReportBounds(report))
	effect := requireType[map[string]any](t, effects[0])
	effect["affected_scopes"] = []string{"/nodes/host", "/nodes/host/runtime", "/nodes"}
	requireNoError(t, json.Unmarshal(requireJSON(t, map[string]any{"content": "{}", "effects": effects}), &report))
	if augmentationReportBounds(report) == nil {
		t.Fatal("scope work above 16384 admitted before report serialization")
	}
}
