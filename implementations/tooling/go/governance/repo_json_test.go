package governance

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestRepositoryPolicyJSONReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Text     string
		Allowed  bool
		Findings []Finding
	}](t, "policy-json-reference") {
		t.Run(tc.Text, func(t *testing.T) {
			root := t.TempDir()
			testWrite(t, root, repoPolicyConfig, []byte(tc.Text))
			r, err := openRepository(root)
			if err != nil {
				t.Fatal(err)
			}
			defer func() { _ = r.root.Close() }()
			value, _, findings := loadRepositoryPolicy(r)
			if (value != nil) != tc.Allowed {
				t.Fatalf("allowed=%v want %v", value != nil, tc.Allowed)
			}
			if diff := cmp.Diff(tc.Findings, findings); diff != "" {
				t.Fatalf("legacy policy JSON (-reference +Go):\n%s", diff)
			}
		})
	}
}
