package analysis

import (
	"testing"
)

func TestCandidateSynthesisAllOrNoneRefusals(t *testing.T) {
	raw := readTestFile(t, "../../../../contracts/fixtures/candidate-synthesis/sdl-candidate-synthesis-input-v1/valid/nist-csf.json")
	for _, tc := range []struct {
		name, disposition string
		change            func(map[string]any)
	}{
		{"unavailable", "non-reproducible", func(v map[string]any) {
			object(v["transformation_profile"])["digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		}},
		{"missing-decision", "requires-decision", func(v map[string]any) { v["decisions"] = []any{} }},
		{"stale-input", "", func(v map[string]any) {
			object(v["source"])["assertion_set_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			input := testObject(t, raw)
			tc.change(input)
			data := testJSON(t, input)
			result, err := Analyze(Request{Kind: "candidate-synthesis", Input: &JSONInput{Data: data}})
			if tc.disposition == "" {
				if err == nil {
					t.Fatal("stale input admitted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if result.Candidate != nil || result.CandidateSource != nil || result.Document["candidate_exact_digest"] != nil || result.Document["disposition"] != tc.disposition {
				t.Fatalf("partial candidate: %v", result.Document)
			}
		})
	}
}

func TestCandidateSynthesisPublishedRefusals(t *testing.T) {
	for _, name := range []string{"ambiguous-ordering", "missing-native-semantics", "non-reproducible-transformation", "stale-input", "unresolved-parameterization", "unsupported-relation"} {
		t.Run(name, func(t *testing.T) {
			checkSynthesisRefusal(t, name)
		})
	}
}

func checkSynthesisRefusal(t *testing.T, name string) {
	t.Helper()
	raw := readTestFile(t, "../../../../contracts/fixtures/candidate-synthesis/sdl-candidate-synthesis-input-v1/invalid/"+name+".json")
	result, err := Analyze(Request{Kind: "candidate-synthesis", Input: &JSONInput{Data: raw}})
	if name == "stale-input" {
		if err == nil {
			t.Fatal("stale input accepted")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	if result.Candidate != nil || result.CandidateSource != nil || result.Document["candidate_exact_digest"] != nil || result.Document["candidate_canonical_digest"] != nil || result.Document["disposition"] == "success" || len(array(result.Document["construct_traces"])) != 0 {
		t.Fatalf("partial candidate: %v", result.Document)
	}
	expected := name
	if name == "non-reproducible-transformation" {
		expected = "transformation-profile-unavailable"
	}
	found := false
	for _, row := range array(result.Document["unresolved_choices"]) {
		if object(row)["reason"] == expected {
			found = true
		}
	}
	if !found {
		t.Fatalf("missing refusal reason %s", expected)
	}
	losses := array(object(result.Document["transformation_report"])["losses"])
	if name == "unsupported-relation" && (len(losses) != 1 || object(losses[0])["kind"] != "semantic-omission") {
		t.Fatal("unsupported relation omitted loss evidence")
	}
}
