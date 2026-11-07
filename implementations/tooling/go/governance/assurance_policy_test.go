package governance

import (
	"os"
	"path/filepath"
	"testing"
)

func TestAssurancePolicyReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []editedPolicyReference
	}](t, "assurance-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkEditedPolicyReference(t, "assurance-policy", fixture.Base, tc) })
	}
}

func TestAssurancePolicyRepository(t *testing.T) {
	report, err := Check(t.Context(), Request{Tool: "assurance-policy", Root: "../../../.."})
	if err != nil || len(report.Findings) > 0 {
		t.Fatalf("repository assurance=%+v, %v", report, err)
	}
}

func TestAssuranceReadErrors(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("root bypasses file read permissions")
	}
	fixture := readReference[struct{ Base map[string]string }](t, "assurance-reference")
	for _, name := range []string{assurancePolicy, assuranceLedger, assuranceFulfillment, assuranceADR, assuranceCoding, assuranceOverview, assuranceTemplate} {
		t.Run(name, func(t *testing.T) {
			root := seedRepositoryReference(t, repositoryReference{Files: fixture.Base})
			selected := filepath.Join(root, name)
			if err := os.Chmod(selected, 0); err != nil {
				t.Fatal(err)
			}
			t.Cleanup(func() {
				if err := os.Chmod(selected, 0o600); err != nil {
					t.Error(err)
				}
			})
			if report, err := Check(t.Context(), Request{Tool: "assurance-policy", Root: root}); err == nil {
				t.Fatalf("operational read error became suppressible: %+v", report)
			}
		})
	}
}
