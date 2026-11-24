package governance

import (
	"maps"
	"testing"
)

type sourceSelectionReference struct {
	Name, ID, Version, URL, RawPath, Digest, Size, ErrorType string
	Valid                                                    bool
	Changes                                                  map[string]*string
	JSONEdits                                                map[string][]referenceJSONEdit
}

func TestSourceSelectionReference(t *testing.T) {
	fixture := readReference[struct {
		Base  map[string]string
		Cases []sourceSelectionReference
	}](t, "source-selection-reference")
	for _, tc := range fixture.Cases {
		t.Run(tc.Name, func(t *testing.T) { checkSourceSelectionReference(t, fixture.Base, tc) })
	}
}
func checkSourceSelectionReference(t *testing.T, base map[string]string, tc sourceSelectionReference) {
	t.Helper()
	changes := referenceJSONEdits(t, base, tc.JSONEdits)
	maps.Copy(changes, tc.Changes)
	root := seedRepositoryReference(t, repositoryReference{Files: deltaFiles(base, changes)})
	r, err := openRepository(root)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	selection, err := selectSourceSnapshot(r, tc.ID, tc.Version)
	if (err == nil) != tc.Valid {
		t.Fatalf("valid=%t want=%t reference=%s native=%v", err == nil, tc.Valid, tc.ErrorType, err)
	}
	if err != nil {
		return
	}
	if selection.url != tc.URL || selection.raw.path != tc.RawPath || selection.raw.digest != tc.Digest || string(selection.raw.size) != tc.Size {
		t.Fatalf("selection=%+v differs from bound reference", selection)
	}
}
