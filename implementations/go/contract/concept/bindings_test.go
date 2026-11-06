package concept

import (
	"encoding/json"
	"errors"
	"io/fs"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

const fixtureRoot = "fixtures/concept-authority/external-concept-bindings-v1/"

// webNode returns the subject that the reference binding fixtures assert.
func webNode() Subject {
	return Subject{SubjectKind: "node", OwningContractID: "sdl-authoring-input-v1", LifecyclePhase: "normalized-authoring", CanonicalRef: "nodes.web", ArtifactDigest: "sha256:a22d5d994e8bd4c4634a884f0f1be2e395c96a5b8efe3ed25e79e8d8847a99ff"}
}

// admitted returns a binding-set value through a validator whose rules for
// the contract accept every document, so the resolver tests do not depend on
// the family rules of contract/admission.
func admitted(t *testing.T, document map[string]any) validation.Value {
	t.Helper()
	shared := schemas(t)
	var rules []validation.Rule
	for _, key := range shared.Keys() {
		if key.ContractID == bindingsContract {
			rules = append(rules, validation.Rule{Key: key, Check: func(validation.Invocation) error { return nil }})
		}
	}
	permissive, err := shared.WithRules(rules)
	if err != nil {
		t.Fatalf("WithRules() error = %v", err)
	}
	data, err := json.Marshal(document)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	value, err := permissive.Validate(bindingsContract, data, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
	return value
}

func fixture(t *testing.T, name string) map[string]any {
	t.Helper()
	source, err := corpus.Open()
	if err != nil {
		t.Fatalf("corpus.Open() error = %v", err)
	}
	data, err := fs.ReadFile(source, fixtureRoot+name)
	if err != nil {
		t.Fatalf("ReadFile(%q) error = %v", name, err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	return document
}

func members(t *testing.T, v any) map[string]any {
	t.Helper()
	m, ok := v.(map[string]any)
	if !ok {
		t.Fatalf("value %T is not a JSON object", v)
	}
	return m
}

func onlyBinding(t *testing.T, document map[string]any) map[string]any {
	t.Helper()
	for _, binding := range members(t, document["bindings"]) {
		return members(t, binding)
	}
	t.Fatal("the fixture has no binding")
	return nil
}

func assertedSubject(t *testing.T, document map[string]any) Subject {
	t.Helper()
	text := func(v any) string { s, _ := v.(string); return s }
	s := members(t, onlyBinding(t, document)["subject"])
	return Subject{SubjectKind: text(s["subject_kind"]), OwningContractID: text(s["owning_contract_id"]), LifecyclePhase: text(s["lifecycle_phase"]), CanonicalRef: text(s["canonical_ref"]), ArtifactDigest: text(s["artifact_digest"])}
}

func admit(t *testing.T, subjects []Subject, document map[string]any, snapshots []SchemeSnapshot) ResolutionOutcome {
	t.Helper()
	outcome, err := mustLoad(t).AdmitBindings(subjects, admitted(t, document), snapshots)
	if err != nil {
		t.Fatalf("AdmitBindings() error = %v", err)
	}
	return outcome
}

func TestValidFixturesResolveCurrentConcepts(t *testing.T) {
	snapshots := mustLoad(t).PinnedSnapshots()
	for _, name := range []string{"activitystreams-behavior.json", "attack-enterprise.json", "fipa-behavior.json", "nist-csf.json"} {
		document := fixture(t, "valid/"+name)
		outcome := admit(t, []Subject{assertedSubject(t, document)}, document, snapshots)
		if !outcome.Admitted() || len(outcome.Results) != 1 || outcome.Results[0].Outcome != ResolvedCurrent || len(outcome.Results[0].Diagnostics) != 0 {
			t.Errorf("%s: AdmitBindings() = %+v, want one active resolved-current result", name, outcome)
		}
	}
}

func TestBindingOutcomesMatchTheReference(t *testing.T) {
	snapshots := mustLoad(t).PinnedSnapshots()
	attack := fixture(t, "valid/attack-enterprise.json")
	staleDigest := webNode()
	staleDigest.ArtifactDigest = "sha256:" + strings.Repeat("b", 64)
	otherRef := webNode()
	otherRef.CanonicalRef = "nodes.db"
	for name, tc := range map[string]struct {
		subjects  []Subject
		document  map[string]any
		snapshots []SchemeSnapshot
		outcome   string
		severity  string
		address   string
	}{
		"stale scheme revision":  {[]Subject{webNode()}, fixture(t, "invalid/stale-scheme-revision.json"), snapshots, Stale, "error", "/bindings/0/scheme"},
		"ambiguous subject":      {[]Subject{webNode(), webNode()}, fixture(t, "invalid/ambiguous-subject.json"), snapshots, Ambiguous, "error", "/bindings/0/subject"},
		"stale subject digest":   {[]Subject{staleDigest}, attack, snapshots, Stale, "error", "/bindings/0/subject"},
		"subject not found":      {[]Subject{otherRef}, attack, snapshots, SubjectNotFound, "error", "/bindings/0/subject"},
		"no subjects":            {nil, attack, snapshots, SubjectNotFound, "error", "/bindings/0/subject"},
		"unavailable scheme":     {[]Subject{webNode()}, attack, nil, Unavailable, "warning", "/bindings/0/scheme"},
		"duplicate snapshots":    {[]Subject{webNode()}, attack, append(snapshots, snapshots...), Ambiguous, "error", "/bindings/0/scheme"},
		"locator mismatch":       {[]Subject{webNode()}, withScheme(t, attack, "source_locator", "https://example.test/other.json"), snapshots, Stale, "error", "/bindings/0/scheme"},
		"digest case is ignored": {[]Subject{webNode()}, withScheme(t, attack, "source_digest", "sha256:"+strings.ToUpper("bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3")), snapshots, ResolvedCurrent, "", ""},
	} {
		t.Run(name, func(t *testing.T) {
			outcome := admit(t, tc.subjects, tc.document, tc.snapshots)
			got := outcome.Results[0]
			if got.Outcome != tc.outcome || got.Active != (tc.outcome == ResolvedCurrent) || outcome.Admitted() != got.Active {
				t.Fatalf("result = %+v, want outcome %s", got, tc.outcome)
			}
			if tc.severity == "" {
				return
			}
			want := []diagnostic.Diagnostic{{Code: "external-concept." + tc.outcome, Severity: tc.severity, Domain: "external-concept-binding", Address: tc.address, Message: got.Diagnostics[0].Message}}
			if diff := cmp.Diff(want, got.Diagnostics); diff != "" {
				t.Errorf("Diagnostics mismatch (-want +got):\n%s", diff)
			}
		})
	}
}

func withScheme(t *testing.T, document map[string]any, field, value string) map[string]any {
	t.Helper()
	var copied map[string]any
	data, err := json.Marshal(document)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	if err := json.Unmarshal(data, &copied); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	members(t, onlyBinding(t, copied)["scheme"])[field] = value
	return copied
}

func TestBindingDiagnosticsDoNotEchoIdentifiers(t *testing.T) {
	snapshots := mustLoad(t).PinnedSnapshots()
	secret := "ATTACKER-CONTROLLED-SECRET"
	unknown := admit(t, []Subject{webNode()}, withScheme(t, fixture(t, "valid/attack-enterprise.json"), "concept_id", secret), snapshots)
	ambiguous := admit(t, []Subject{webNode(), webNode()}, fixture(t, "invalid/ambiguous-subject.json"), snapshots)
	if got := unknown.Results[0]; got.Outcome != UnknownConcept || strings.Contains(got.Diagnostics[0].Message, secret) || got.ResolvedConceptID != nil {
		t.Errorf("unknown concept result = %+v, want unknown-concept without the identifier", got)
	}
	if message := ambiguous.Results[0].Diagnostics[0].Message; strings.Contains(message, "nodes.web") {
		t.Errorf("ambiguous subject message = %q, want no subject reference", message)
	}
}

func TestSupersededConceptIsNotRewritten(t *testing.T) {
	snapshots := mustLoad(t).PinnedSnapshots()
	for i := range snapshots {
		for j, term := range snapshots[i].Concepts {
			if term.ConceptID == "TA0002" {
				snapshots[i].Concepts[j] = SnapshotTerm{ConceptID: "TA0002", Status: "superseded", SuccessorConceptIDs: []string{"TA9999"}}
			}
		}
	}
	got := admit(t, []Subject{webNode()}, fixture(t, "valid/attack-enterprise.json"), snapshots).Results[0]
	if got.Outcome != Superseded || got.Active || got.ResolvedConceptID == nil || *got.ResolvedConceptID != "TA0002" {
		t.Errorf("result = %+v, want inactive superseded TA0002", got)
	}
}

func TestDuplicateCandidatesAreAmbiguous(t *testing.T) {
	snapshots := mustLoad(t).PinnedSnapshots()
	for i := range snapshots {
		if snapshots[i].SchemeID == "mitre-attack-enterprise-tactics" {
			snapshots[i].Concepts = append(snapshots[i].Concepts, SnapshotTerm{ConceptID: "TA0002", Status: "current"})
		}
	}
	got := admit(t, []Subject{webNode()}, fixture(t, "valid/attack-enterprise.json"), snapshots).Results[0]
	if got.Outcome != Ambiguous || got.Active || strings.Contains(got.Diagnostics[0].Message, "TA0002") {
		t.Errorf("result = %+v, want ambiguous without the concept identifier", got)
	}
}

func TestBindingsResolveInIDOrder(t *testing.T) {
	document := fixture(t, "valid/attack-enterprise.json")
	binding := onlyBinding(t, document)
	document["bindings"] = map[string]any{"z-binding": binding, "a-binding": binding}
	outcome := admit(t, []Subject{webNode()}, document, nil)
	var got []string
	for _, r := range outcome.Results {
		got = append(got, r.BindingID+" "+r.Diagnostics[0].Address)
	}
	if diff := cmp.Diff([]string{"a-binding /bindings/0/scheme", "z-binding /bindings/1/scheme"}, got); diff != "" {
		t.Errorf("results mismatch (-want +got):\n%s", diff)
	}
	if outcome.BindingSetID != "portable-scheme-examples" {
		t.Errorf("BindingSetID = %q, want portable-scheme-examples", outcome.BindingSetID)
	}
}

func TestAdmittedNeedsAResult(t *testing.T) {
	if (ResolutionOutcome{}).Admitted() {
		t.Errorf("empty outcome Admitted() = true, want false")
	}
}

func TestAdmitBindingsRefusesUnadmittedDocuments(t *testing.T) {
	for name, value := range map[string]validation.Value{"zero value": {}} {
		_, err := mustLoad(t).AdmitBindings(nil, value, nil)
		if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
			t.Errorf("%s: AdmitBindings() error = %v, want an InvalidInput fault", name, err)
		}
	}
	shared := schemas(t)
	var families []byte
	for _, document := range mustLoad(t).Documents() {
		if document.ContractID == "concept-families-v1" {
			families = document.JSON
		}
	}
	other, err := shared.Validate("concept-families-v1", families, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatalf("Validate(concept-families-v1) error = %v", err)
	}
	if _, err := mustLoad(t).AdmitBindings(nil, other, nil); err == nil {
		t.Errorf("AdmitBindings(other contract) error = nil, want refusal")
	}
}

func TestSchemeSnapshotLocatorsAreInert(t *testing.T) {
	base := mustLoad(t).PinnedSnapshots()[0]
	document := fixture(t, "valid/attack-enterprise.json")
	mutations := map[string]func(*SchemeSnapshot){
		"relative locator":   func(s *SchemeSnapshot) { s.SourceLocator = "relative/path.json" },
		"file locator":       func(s *SchemeSnapshot) { s.SourceLocator = "file:///tmp/scheme.json" },
		"data locator":       func(s *SchemeSnapshot) { s.SourceLocator = "data:application/json,%7B%7D" },
		"credential locator": func(s *SchemeSnapshot) { s.SourceLocator = "https://user:password@example.test/scheme.json" },
		"secret query":       func(s *SchemeSnapshot) { s.SourceLocator = "https://example.test/scheme.json?access_token=secret" },
		"fragment":           func(s *SchemeSnapshot) { s.SourceLocator = "https://example.test/scheme.json#concept" },
		"empty scheme":       func(s *SchemeSnapshot) { s.SchemeID = "" },
		"empty authority":    func(s *SchemeSnapshot) { s.Authority = "" },
		"empty revision":     func(s *SchemeSnapshot) { s.Revision = "" },
		"bad digest":         func(s *SchemeSnapshot) { s.SourceDigest = "sha256:abc" },
		"no concepts":        func(s *SchemeSnapshot) { s.Concepts = nil },
		"empty concept":      func(s *SchemeSnapshot) { s.Concepts = []SnapshotTerm{{Status: "current"}} },
		"current with successor": func(s *SchemeSnapshot) {
			s.Concepts = []SnapshotTerm{{ConceptID: "a", Status: "current", SuccessorConceptIDs: []string{"b"}}}
		},
		"superseded alone": func(s *SchemeSnapshot) { s.Concepts = []SnapshotTerm{{ConceptID: "a", Status: "superseded"}} },
		"repeated successor": func(s *SchemeSnapshot) {
			s.Concepts = []SnapshotTerm{{ConceptID: "a", Status: "superseded", SuccessorConceptIDs: []string{"b", "b"}}}
		},
		"empty successor": func(s *SchemeSnapshot) {
			s.Concepts = []SnapshotTerm{{ConceptID: "a", Status: "superseded", SuccessorConceptIDs: []string{""}}}
		},
		"unknown status": func(s *SchemeSnapshot) { s.Concepts = []SnapshotTerm{{ConceptID: "a", Status: "retired"}} },
	}
	for name, mutate := range mutations {
		snapshot := base.copy()
		mutate(&snapshot)
		_, err := mustLoad(t).AdmitBindings([]Subject{webNode()}, admitted(t, document), []SchemeSnapshot{snapshot})
		var typed *fault.Error
		if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput || !errorsAs(err, &typed) || typed.Code() != "external-concept-input-invalid" {
			t.Errorf("%s: AdmitBindings() error = %v, want InvalidInput external-concept-input-invalid", name, err)
		}
	}
	valid := base.copy()
	valid.Concepts = []SnapshotTerm{{ConceptID: "a", Status: "superseded", SuccessorConceptIDs: []string{"b", "c"}}}
	if _, err := mustLoad(t).AdmitBindings([]Subject{webNode()}, admitted(t, document), []SchemeSnapshot{valid}); err != nil {
		t.Errorf("AdmitBindings(superseded with successors) error = %v, want nil", err)
	}
}

func TestSubjectsFollowThePublishedDefinition(t *testing.T) {
	document := fixture(t, "valid/attack-enterprise.json")
	for name, mutate := range map[string]func(*Subject){
		"bad digest":      func(s *Subject) { s.ArtifactDigest = "sha256:abc" },
		"empty kind":      func(s *Subject) { s.SubjectKind = "" },
		"unknown phase":   func(s *Subject) { s.LifecyclePhase = "unknown-phase" },
		"empty reference": func(s *Subject) { s.CanonicalRef = "" },
	} {
		subject := webNode()
		mutate(&subject)
		_, err := mustLoad(t).AdmitBindings([]Subject{subject}, admitted(t, document), nil)
		if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
			t.Errorf("%s: AdmitBindings() error = %v, want an InvalidInput fault", name, err)
		}
	}
}

func errorsAs(err error, target **fault.Error) bool { return errors.As(err, target) }
