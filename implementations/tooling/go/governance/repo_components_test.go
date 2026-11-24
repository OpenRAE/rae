package governance

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

type repoComponentReference struct {
	Name, Part, Policy, CheckSet, Error string
	Files                               map[string]string
	Changed                             []string
	Findings                            []Finding
}

func TestRepoPolicyComponentsReference(t *testing.T) {
	for _, tc := range readReference[[]repoComponentReference](t, "repo-components-reference") {
		t.Run(tc.Name, func(t *testing.T) { checkRepoComponentReference(t, tc) })
	}
}

func checkRepoComponentReference(t *testing.T, tc repoComponentReference) {
	t.Helper()

	root := seedRepositoryReference(t, repositoryReference{Files: tc.Files})
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	value, err := yamlValue([]byte(tc.Policy), true)
	if err != nil {
		t.Fatal(err)
	}
	policy := object(value)
	var findings []Finding
	if tc.Part == "size" {
		findings, err = repoLayerAndSize(t.Context(), r, policy, tc.Changed)
	} else {
		findings, err = repoModules(t.Context(), r, policy, tc.Changed, tc.CheckSet)
	}
	if tc.Error != "" {
		if err == nil {
			t.Fatalf("source error became a verdict: %+v", findings)
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if diff := cmp.Diff(tc.Findings, findings); diff != "" {
		t.Fatalf("findings (-source +native):\n%s", diff)
	}
}
