package governance

import (
	"errors"
	"testing"
	"testing/fstest"
)

func TestDocumentationProtectedSubtree(t *testing.T) {
	// In-memory names exercise refusal without creating or accessing a secret
	// directory or reading any user's files.
	tree := fstest.MapFS{"site/_downloads/.secrets/payload": {Data: []byte("inert fixture")}}
	_, err := walkDocumentationEntries(tree, "site/_downloads", "site/_downloads")
	if !errors.Is(err, errUnsafePath) {
		t.Fatalf("protected subtree became empty successful inventory: %v", err)
	}
}

func TestDocumentationOutputDisplay(t *testing.T) {
	for _, tc := range []struct{ selection, want string }{
		{"site", "site/searchindex.js"}, {"./site/", "site/searchindex.js"},
		{"out/../site", "out/../site/searchindex.js"}, {"/tmp/site", "/tmp/site/searchindex.js"},
		{".", "searchindex.js"}, {"/", "/searchindex.js"}, {"//host/site", "//host/site/searchindex.js"},
	} {
		if got := publicOutputDisplay(tc.selection, "searchindex.js"); got != tc.want {
			t.Errorf("display %q=%q want %q", tc.selection, got, tc.want)
		}
	}
}
