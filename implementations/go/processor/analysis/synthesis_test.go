package analysis

import (
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestCandidateSynthesisPublishedRecords(t *testing.T) {
	for _, name := range []string{"nist-csf", "attack-enterprise"} {
		t.Run(name, func(t *testing.T) {
			root := "../../../../contracts/fixtures/candidate-synthesis/"
			input := readTestFile(t, root+"sdl-candidate-synthesis-input-v1/valid/"+name+".json")
			expected := readTestFile(t, root+"sdl-candidate-synthesis-record-v1/valid/"+name+".json")
			want := testObject(t, expected)
			got, err := Analyze(Request{Kind: "candidate-synthesis", Input: &JSONInput{Data: input}})
			if err != nil {
				t.Fatal(err)
			}
			if diff := cmp.Diff(want, got.Document); diff != "" {
				t.Fatal(diff)
			}
			if got.Candidate == nil || got.CandidateSource == nil {
				t.Fatal("successful synthesis omitted candidate")
			}
		})
	}
}
