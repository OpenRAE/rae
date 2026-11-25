package analysis

import (
	"testing"
)

func TestOpacityKernelKeepsEveryObserverCoordinate(t *testing.T) {
	secret := opacityPoint{Ordinal: 0, Secret: true, Initial: "initial", Observation: "observed", Memory: "memory", Release: "released", Strategy: "strategy", Order: "order"}
	decoy := secret
	decoy.Ordinal = 1
	decoy.Secret = false
	got := opacityKernel([]opacityPoint{decoy, secret})
	if got.counterexample != nil || got.checked != 2 || got.secret != 1 {
		t.Fatalf("%+v", got)
	}
	changes := []func(*opacityPoint){func(p *opacityPoint) { p.Initial = "other" }, func(p *opacityPoint) { p.Observation = "other" }, func(p *opacityPoint) { p.Memory = "other" }, func(p *opacityPoint) { p.Release = "other" }, func(p *opacityPoint) { p.Strategy = "other" }, func(p *opacityPoint) { p.Order = "other" }, func(p *opacityPoint) { v := "coalition"; p.Coalition = &v }}
	for _, change := range changes {
		other := decoy
		change(&other)
		got = opacityKernel([]opacityPoint{other, secret})
		if got.counterexample == nil || *got.counterexample != 0 || got.cellSize != 1 {
			t.Fatalf("coordinate collapsed: %+v", got)
		}
	}
	high := secret
	high.Ordinal = 4
	got = opacityKernel([]opacityPoint{high, secret})
	if got.counterexample == nil || *got.counterexample != 0 || got.checked != 2 || got.secret != 2 || got.cellSize != 2 {
		t.Fatalf("scan ended early: %+v", got)
	}
}
func TestBoundedOpacityFixtureAndRefusals(t *testing.T) {
	raw := readTestFile(t, "../../../../contracts/fixtures/formal-analysis/participant-opacity-analysis-input-v1/valid/opaque-pair.json")
	for _, test := range []struct {
		name, outcome string
		change        func(map[string]any)
	}{
		{"opaque", "no-counterexample-within-declared-finite-bounds", func(map[string]any) {}},
		{"counterexample", "counterexample-found", func(v map[string]any) { object(array(v["points"])[1])["observation_key"] = "observation:other" }},
		{"vacuous", "vacuous-secret-domain", func(v map[string]any) { object(array(v["points"])[0])["secret_holds"] = false }},
		{"incomplete", "unsupported", func(v map[string]any) { v["complete_enumeration"] = false }},
		{"bad-profile", "", func(v map[string]any) {
			v["profile_digest"] = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		}},
	} {
		t.Run(test.name, func(t *testing.T) {
			document := testObject(t, raw)
			test.change(document)
			data := testJSON(t, document)
			result, err := Analyze(Request{Kind: "participant-opacity", Input: &JSONInput{Data: data}})
			if test.outcome == "" {
				if err == nil {
					t.Fatal("profile forgery admitted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if result.Document["outcome"] != test.outcome {
				t.Fatalf("got %v", result.Document)
			}
		})
	}
}
