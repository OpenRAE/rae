package admission

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

type flowReferenceFixture struct {
	OwnerReleaseAuthorities []FlowOwnerReleaseAuthority `json:"OwnerReleaseAuthorities"`
	OwnerSink               FlowOwnerSink               `json:"OwnerSink"`
	Relation                json.RawMessage             `json:"Relation"`
	Profile                 json.RawMessage             `json:"Profile"`
	Plane                   json.RawMessage             `json:"Plane"`
	Manifest                json.RawMessage             `json:"Manifest"`
	ImplementationSelection json.RawMessage             `json:"ImplementationSelection"`
	Selection               FlowActionSelection         `json:"Selection"`
	Sources                 map[string]json.RawMessage  `json:"Sources"`
	Cuts                    map[string]json.RawMessage  `json:"Cuts"`
	Crossings               []json.RawMessage           `json:"Crossings"`
	Subjects                []json.RawMessage           `json:"Subjects"`
	Policies                []json.RawMessage           `json:"Policies"`
	Controls                []json.RawMessage           `json:"Controls"`
	Declarations            []ControlDeclaration        `json:"Declarations"`
	Authorities             []FlowReleaseAuthority      `json:"Authorities"`
	Sink                    FlowSink                    `json:"Sink"`
	Evidence                []string                    `json:"Evidence"`
	Authority               []string                    `json:"Authority"`
	ActionResolution        FlowActionResolution        `json:"ActionResolution"`
	CapabilityResolution    FlowCapabilityResolution    `json:"CapabilityResolution"`
	HistoryResolution       FlowHistoryResolution       `json:"HistoryResolution"`
	ActionEvidence          []string                    `json:"ActionEvidence"`
	ActionBoundaryEvidence  []string                    `json:"ActionBoundaryEvidence"`
	ObservationBoundary     string                      `json:"ObservationBoundary"`
}

func TestOwnerFlowRequiresEachObligationAuthorityAndExactReader(t *testing.T) {
	e := boundTestOwner(t)
	_, c := flowContextFixture(t, e)
	raw, err := os.ReadFile("testdata/flow-owner-resolution.json")
	if err != nil {
		t.Fatal(err)
	}
	var golden flowReferenceFixture
	if err = json.Unmarshal(raw, &golden); err != nil {
		t.Fatal(err)
	}
	c.snapshot.Profile, c.snapshot.SourceLabels = golden.Profile, flowRawMap(golden.Sources)
	c.snapshot.OwnerReleaseAuthorities = golden.OwnerReleaseAuthorities
	c.snapshot.OwnerSinks = map[FlowSink]FlowOwnerSink{c.snapshot.KnownSinks[0]: golden.OwnerSink}
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if _, err = e.Validate("participant-flow-control-relation-v1", golden.Relation, limits, c); err != nil {
		t.Fatal(err)
	}
	c.snapshot.OwnerReleaseAuthorities = golden.OwnerReleaseAuthorities[:1]
	if _, err = e.Validate("participant-flow-control-relation-v1", golden.Relation, limits, c); err == nil {
		t.Error("accepted missing per-obligation owner grant")
	}
	c.snapshot.OwnerReleaseAuthorities = golden.OwnerReleaseAuthorities
	sink := golden.OwnerSink
	sink.Readers = []string{"reader:alice"}
	c.snapshot.OwnerSinks[c.snapshot.KnownSinks[0]] = sink
	if _, err = e.Validate("participant-flow-control-relation-v1", golden.Relation, limits, c); err == nil {
		t.Error("accepted a sink outside owner-b's readers")
	}
}

type flowTestContext struct {
	crossingTestContext
	controlOccurrenceTestContext

	snapshot            FlowControlSnapshot
	evidence, authority []string
}

func (c *flowTestContext) FlowControlSnapshot() FlowControlSnapshot { return c.snapshot }
func (c *flowTestContext) CrossingEvidenceRefs() []string           { return c.evidence }
func (c *flowTestContext) CrossingAuthorityRefs() []string          { return c.authority }

func flowRawList(rows []json.RawMessage) [][]byte {
	result := make([][]byte, len(rows))
	for index, row := range rows {
		result[index] = row
	}
	return result
}
func flowRawMap(rows map[string]json.RawMessage) map[string][]byte {
	result := map[string][]byte{}
	for key, row := range rows {
		result[key] = row
	}
	return result
}

func flowContextFixture(t *testing.T, e *Validator) ([]byte, *flowTestContext) {
	t.Helper()
	// Generated from test_sem_233_flow_control_contracts._validation_context.
	// Python's full owner admission passed before recording this synthetic data.
	raw, err := os.ReadFile("testdata/flow-resolution.json")
	if err != nil {
		t.Fatal(err)
	}
	var golden flowReferenceFixture
	if err = json.Unmarshal(raw, &golden); err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	manifest, err := e.Validate("participant-implementation-manifest-v1", golden.Manifest, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	plane, err := e.Validate("runtime-fact-binding-plane-v1", golden.Plane, limits, nil)
	if err != nil {
		t.Fatal(err)
	}
	selection := golden.Selection
	a := golden.ActionResolution
	request := FlowActionRequest{ParticipantAddress: a.ParticipantAddress, ActionContractAddress: a.ActionContractAddress, ActionInstanceID: a.ActionInstanceID, ObservationBoundaryAddress: golden.ObservationBoundary, Manifest: manifest, ImplementationSelection: golden.ImplementationSelection, Selection: &selection, EvidenceRefs: golden.ActionEvidence, ObservationBoundaryEvidenceRefs: golden.ActionBoundaryEvidence}
	s := FlowControlSnapshot{Profile: golden.Profile, SourceLabels: flowRawMap(golden.Sources), PolicyCuts: flowRawMap(golden.Cuts), ReleaseAuthorities: golden.Authorities, KnownSinks: []FlowSink{golden.Sink}, RuntimeFactPlanes: map[string]validation.Value{"runtime-fact-plane.1": plane}, ActionSelections: map[[2]string]FlowActionSelection{{selection.ActionContractAddress, selection.ProposalRef}: selection}, ActionAdmissions: map[string]FlowActionRequest{a.Reference: request}, ActionResolutions: map[string]FlowActionResolution{a.Reference: a}, CapabilityResolutions: map[string]FlowCapabilityResolution{golden.CapabilityResolution.Reference: golden.CapabilityResolution}, HistoryResolutions: []FlowHistoryResolution{golden.HistoryResolution}}
	c := &flowTestContext{crossingTestContext: crossingTestContext{records: flowRawList(golden.Crossings), subjects: flowRawList(golden.Subjects), policies: flowRawList(golden.Policies)}, controlOccurrenceTestContext: controlOccurrenceTestContext{records: flowRawList(golden.Controls), declarations: golden.Declarations}, snapshot: s, evidence: golden.Evidence, authority: golden.Authority}
	return golden.Relation, c
}

func TestFlowResolvedContextRequiresExactIncumbentOwners(t *testing.T) {
	e := boundTestOwner(t)
	raw, c := flowContextFixture(t, e)
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	if _, err := e.Validate("participant-flow-control-relation-v1", raw, limits, c); err != nil {
		t.Fatal(err)
	}
	for _, name := range []string{"profile", "sources", "cuts", "release-authority", "planes", "selections", "admissions", "capability", "history", "control", "crossing", "evidence"} {
		t.Run(name, func(t *testing.T) {
			raw, changed := flowContextFixture(t, e)
			flowContextMutation(changed, name)
			if _, err := e.Validate("participant-flow-control-relation-v1", raw, limits, changed); err == nil {
				t.Fatal("accepted unsubstantiated owner claim")
			}
		})
	}
}

func flowContextMutation(c *flowTestContext, name string) {
	switch name {
	case "profile":
		c.snapshot.Profile = []byte(`{}`)
	case "sources":
		c.snapshot.SourceLabels = nil
	case "cuts":
		c.snapshot.PolicyCuts = nil
	case "release-authority":
		c.snapshot.ReleaseAuthorities = nil
	case "planes":
		c.snapshot.RuntimeFactPlanes = nil
	case "selections":
		c.snapshot.ActionSelections = nil
	case "admissions":
		c.snapshot.ActionAdmissions = nil
	case "capability":
		c.snapshot.CapabilityResolutions = nil
	case "history":
		c.snapshot.HistoryResolutions = nil
	case "control":
		c.controlOccurrenceTestContext.records = nil
	case "crossing":
		c.crossingTestContext.records = nil
	case "evidence":
		c.evidence = nil
	}
}
