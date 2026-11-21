package sdl

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func TestEnvelopeProbesMatchPythonReference(t *testing.T) {
	raw, err := os.ReadFile("../contract/admission/testdata/backend/probe-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []probeReference
	if json.Unmarshal(raw, &cases) != nil || len(cases) != 18 {
		t.Fatal("reference")
	}
	for _, test := range cases {
		t.Run(test.Name+map[bool]string{true: "-positive", false: "-negative"}[test.Positive], func(t *testing.T) {
			checkProbeReference(t, test)
		})
	}
}

type probeReference struct {
	Name     string                        `json:"name"`
	Positive bool                          `json:"positive"`
	Envelope binding.RealizationEnvelopeV1 `json:"envelope"`
	Probes   []struct {
		Path      string `json:"path"`
		Variation string `json:"variation"`
		Digest    string `json:"digest"`
		Kind      string `json:"domain_kind"`
		Payload   any    `json:"payload"`
	} `json:"probes"`
	Diagnostics []probeFinding `json:"diagnostics"`
}

func checkProbeReference(t *testing.T, test probeReference) {
	t.Helper()
	probes, findings, err := EnvelopeProbes(test.Envelope, test.Positive)
	if err != nil {
		t.Fatal(err)
	}
	if len(probes) != len(test.Probes) || len(findings) != len(test.Diagnostics) {
		t.Fatalf("probes=%d want=%d findings=%+v", len(probes), len(test.Probes), findings)
	}
	checkProbeFindings(t, findings, test.Diagnostics)
	for i, want := range test.Probes {
		got := probes[i]
		if got.Path != want.Path || got.DomainKind != want.Kind || got.Variation != want.Variation || got.Digest != want.Digest {
			t.Fatalf("probe %d %+v want %+v", i, got, want)
		}
		raw, err := json.Marshal(got.Payload.Document())
		if err != nil {
			t.Fatal(err)
		}
		var payload any
		if json.Unmarshal(raw, &payload) != nil {
			t.Fatal("payload")
		}
		if diff := cmp.Diff(want.Payload, payload); diff != "" {
			t.Fatal(diff)
		}
		checkProbeMembership(t, got.Scenario, test.Envelope, test.Positive)
	}
}

func checkProbeMembership(t *testing.T, scenario InstantiatedScenario, envelope binding.RealizationEnvelopeV1, positive bool) {
	t.Helper()
	membership, err := EnvelopeMembershipDiagnostics(scenario, envelope)
	if err != nil || (len(membership) == 0) != positive {
		t.Fatal("unsafe probe", membership, err)
	}
}

type probeFinding struct {
	Code    string `json:"code"`
	Address string `json:"address"`
	Message string `json:"message"`
}

func checkProbeFindings(t *testing.T, got []diagnostic.Diagnostic, want []probeFinding) {
	t.Helper()
	actual := make([]probeFinding, len(got))
	for i, finding := range got {
		actual[i] = probeFinding{Code: finding.Code, Address: finding.Address, Message: finding.Message}
	}
	if diff := cmp.Diff(want, actual); diff != "" {
		t.Fatal(diff)
	}
}
