package admission

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

type controlResolutionTestContext struct {
	crossingTestContext
	controlOccurrenceTestContext

	snapshot           ControlResolutionSnapshot
	refusal, panicHost bool
}

func (c *controlResolutionTestContext) ControlResolutionSnapshot() ControlResolutionSnapshot {
	if c.panicHost {
		panic("private-owner-state")
	}
	return c.snapshot
}
func (c *controlResolutionTestContext) ControlDeclaredSupport(_, support json.RawMessage) (string, error) {
	if c.refusal {
		return "", errors.New("private-owner-state")
	}
	v, err := ingress.Parse(support, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}, ingress.Object)
	return stringAt(v, "declared_level"), err
}
func (c *controlResolutionTestContext) ControlSatisfiedSupport(_ json.RawMessage) (bool, error) {
	return !c.refusal, nil
}

func controlResolutionFixture(t *testing.T, e *Validator, version, name string) (any, *controlResolutionTestContext) {
	t.Helper()
	id := "participant-control-evaluation-" + version
	root := controlResolutionTestRecord(t, id, version, name)
	return controlResolutionOwner(t, e, version, root)
}

func controlResolutionOwner(t *testing.T, e *Validator, version string, root any) (any, *controlResolutionTestContext) {
	t.Helper()
	id := "participant-control-evaluation-" + version
	v, err := e.defaulted(id, root)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile("testdata/control-resolution-crossing.json")
	if err != nil {
		t.Fatal(err)
	}
	crossing, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		t.Fatal(err)
	}
	s := ControlResolutionSnapshot{AdmittedRequest: controlJSON(t, at(v, "request")), IncumbentGateDisposition: "permit", InstalledBindings: map[string][]byte{}, EffectiveSupport: map[string][]byte{}, ResolvedResults: map[string][]byte{}, ResolvedCoverage: map[string][]byte{}, ResolvedSupport: map[[2]string][]byte{}, AuthorizedEffects: map[string][]byte{}, RealizationReceipts: map[string][]byte{}, AuthorizedStateProposals: map[string][]byte{}, InjectOwners: map[string]ControlInjectOwner{}}
	for _, binding := range array(at(v, "request", "selection", "bindings")) {
		s.InstalledBindings[stringAt(binding, "instance_id")] = controlJSON(t, binding)
	}
	controlResolutionTestResults(t, &s, v, version)
	for _, support := range array(at(v, "support")) {
		if version == "v2" {
			s.ResolvedSupport[[2]string{stringAt(support, "obligation_id"), stringAt(support, "instance_id")}] = controlJSON(t, support)
		} else {
			s.EffectiveSupport[stringAt(support, "instance_id")] = controlJSON(t, support)
		}
	}
	for _, coverage := range array(at(v, "request", "applicability", "coverage")) {
		s.ResolvedCoverage[stringAt(coverage, "obligation_id")] = controlJSON(t, coverage)
	}
	if version == "v2" {
		s.AdmittedCrossing = controlJSON(t, at(v, "request", "context", "crossing"))
	} else {
		s.IncumbentGateEvidence = controlJSON(t, at(v, "composition", "incumbent_gate_evidence"))
	}
	if err = e.low.CheckInstances(id, controlJSON(t, v), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, func(i validation.SchemaInstance) error {
		if i.SchemaPointer == "#/$defs/ControlArtifactReferenceModel" {
			s.SafeReferences = append(s.SafeReferences, controlJSON(t, i.Value))
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	s.InjectOwners["delivery-binding"] = ControlInjectOwner{Digest: "sha256:a2660d7ebc60e263919883ce760d1b92b531dc292e4579e1f4cb30ad90a27579", ParticipantAddress: "participants.student", InjectRef: "inject-1", EventRef: "event-inject-1", ScriptRef: "script-1", StoryRef: "story-1", SourceItemRef: "reflection-source", ResultItemRef: "reflection-result", DisclosureRef: "disclosure-1", AudienceScopeRef: "student-audience"}

	c := &controlResolutionTestContext{crossingTestContext: crossingTestContext{records: [][]byte{raw}, subjects: [][]byte{controlJSON(t, at(crossing, "occurrence", "subject"))}, policies: [][]byte{controlJSON(t, at(crossing, "occurrence", "policy"))}}, snapshot: s}
	return v, c
}

func TestControlResolvedContextBindsIndependentOwners(t *testing.T) {
	e := boundTestOwner(t)
	for _, test := range []struct{ version, name string }{{"v1", "teaching-inject"}, {"v2", "dependency-chain"}} {
		t.Run(test.version, func(t *testing.T) {
			v, c := controlResolutionFixture(t, e, test.version, test.name)
			i := validation.Invocation{Key: validation.Key{ContractID: "participant-control-evaluation-" + test.version}, Instance: v, Context: c}
			if _, err := e.Validate(i.Key.ContractID, controlJSON(t, v), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, c); err != nil {
				t.Fatal(err)
			}
			if err := validateTestDocument(t, e, i.Key.ContractID, i.Instance, i.Context); err != nil {
				t.Fatal(err)
			}
			for _, mutation := range []string{"safe", "bindings", "results", "gate", "support", "panic"} {
				_, changed := controlResolutionFixture(t, e, test.version, test.name)
				controlResolutionTestMutation(changed, mutation)
				i.Context = changed
				if err := validateTestDocument(t, e, i.Key.ContractID, i.Instance, i.Context); err == nil {
					t.Errorf("accepted missing owner %s", mutation)
				} else if strings.Contains(err.Error(), "private-owner-state") {
					t.Fatal("leaked private host data")
				}
			}
		})
	}
}

func controlResolutionTestResults(t *testing.T, s *ControlResolutionSnapshot, v any, version string) {
	t.Helper()
	for _, result := range array(at(v, "results")) {
		key := "result_id"
		if version == "v2" {
			key = "slot_id"
		}
		s.ResolvedResults[stringAt(result, key)] = controlJSON(t, result)
		if stringAt(result, "payload", "kind") == "effect-request" {
			effect := at(result, "payload")
			digest, err := controlDigest(effect)
			if err != nil {
				t.Fatal(err)
			}
			s.AuthorizedEffects[digest] = controlJSON(t, at(v, "request", "context"))
		}
	}
}

func controlResolutionTestMutation(c *controlResolutionTestContext, mutation string) {
	switch mutation {
	case "safe":
		c.snapshot.SafeReferences = nil
	case "bindings":
		c.snapshot.InstalledBindings = nil
	case "results":
		c.snapshot.ResolvedResults = nil
	case "gate":
		c.snapshot.IncumbentGateDisposition = "deny"
	case "support":
		c.refusal = true
	case "panic":
		c.panicHost = true
	}
}

func controlResolutionTestRecord(t *testing.T, id, version, name string) any {
	t.Helper()
	root := fixtureObject(t, "fixtures/participant-runtime/"+id+"/valid/"+name+".json")
	if version == "v1" {
		// Generated by Python test_api_424_control_resolution.record_and_context;
		// its full owner check passed before this synthetic golden was recorded.
		raw, err := os.ReadFile("testdata/control-resolution-v1.json")
		if err != nil {
			t.Fatal(err)
		}
		parsed, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 1048576, MaxDepth: 64}, ingress.Object)
		if err != nil {
			t.Fatal(err)
		}
		root = object(parsed)
	}

	return root
}
