package source

import (
	"strings"
	"testing"
)

func TestSharedDiagnosticPathsFollowEscapedPointerOrder(t *testing.T) {
	root := rootPath(nil)
	paths := []*sourcePath{root, root.child("a"), root.child("a0"), root.child("a/b"), root.child("a~b"), root.child("b")}
	paths = append(paths, root.child("a").child("x"), root.child("a").child("x").child("z"), root.child("a").child("/"), root.child("a").child("~"), root.child("b").child("0"))
	for _, left := range paths {
		for _, right := range paths {
			got, want := comparePaths(left, right), strings.Compare(left.pointer(), right.pointer())
			if (got < 0) != (want < 0) || (got > 0) != (want > 0) {
				t.Fatalf("diagnostic path order %q/%q: %d, want sign %d", left.pointer(), right.pointer(), got, want)
			}
		}
	}
	if root.child("a") != paths[1] {
		t.Fatal("shared diagnostic prefix was duplicated")
	}
}
