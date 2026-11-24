package governance

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestADRReferenceParity(t *testing.T) {
	for _, tc := range readReference[[]repositoryReference](t, "adr-reference") {
		t.Run(tc.Name, func(t *testing.T) { runRepositoryReference(t, "adr-immutability", tc) })
	}
}

func TestADRCanonicalReference(t *testing.T) {
	cases := readReference[[]struct {
		Text string   `json:"Text"`
		Hash string   `json:"Hash"`
		Refs []string `json:"Refs"`
	}](t, "adr-content-reference")
	for i, tc := range cases {
		if got := adrHash(tc.Text); got != tc.Hash {
			t.Errorf("case %d: hash=%s, want %s", i, got, tc.Hash)
		}
		if diff := cmp.Diff(tc.Refs, amendmentRefs(tc.Text)); diff != "" {
			t.Errorf("case %d: references (-want +got):\n%s", i, diff)
		}
	}
}
