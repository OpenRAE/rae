package admission

import (
	"compress/gzip"
	"encoding/json"
	"io"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestTrialPlanAcceptsLargeIndependentSealedEntrySet(t *testing.T) {
	file, err := os.Open("testdata/large-trial-plan.json.gz")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = file.Close() }()
	reader, err := gzip.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = reader.Close() }()
	raw, err := io.ReadAll(io.LimitReader(reader, 32<<20))
	if err != nil {
		t.Fatal(err)
	}
	owner := boundTestOwner(t)
	if _, err := owner.trialConstructed(raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}); err != nil {
		t.Fatal("large plan constructor:", err)
	}
	if _, err := owner.Validate("admitted-trial-plan-v1", raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil); err != nil {
		t.Fatal("valid 600-entry plan was refused:", err)
	}
}

func TestTrialSealingRejectsMalformedEntryWithoutPanicking(t *testing.T) {
	owner := boundTestOwner(t)
	for _, raw := range []string{`{"entries":{"x":null}}`, `{"entries":{"x":[]}}`, `{"entries":{"x":"private-marker"}}`} {
		if _, err := SealTrialPlan(owner, []byte(raw), ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}); err == nil {
			t.Fatal("accepted malformed trial entry")
		}
	}
}

func TestTrialSealingMatchesIndependentConstructors(t *testing.T) {
	t.Parallel()
	owner := boundTestOwner(t)
	var reference struct {
		Cases []trialSealingReferenceCase
	}
	readFullReferenceJSON(t, "testdata/trial-plan-projections.json", &reference)
	if len(reference.Cases) != 4 {
		t.Fatal("trial reference inventory changed")
	}
	for _, c := range reference.Cases {
		t.Run(c.Path, func(t *testing.T) { checkTrialSealingReference(t, c, owner) })
	}
	if _, err := TrialPlanProjection(owner, validation.Value{}, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}); err == nil {
		t.Fatal("accepted zero handle")
	}
}

func TestTrialSealingRejectsContradictoryAuthority(t *testing.T) {
	owner := boundTestOwner(t)
	fields := fixtureObject(t, "fixtures/plans/admitted-trial-plan-v1/valid/minimal.json")
	object(fields["admission"])["entry_count"] = json.Number("2")
	raw, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := SealTrialPlan(owner, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}); err == nil {
		t.Fatal("sealed contradictory cardinality")
	}
}

func TestTrialInputFragmentConstructsNativeDefaults(t *testing.T) {
	owner := boundTestOwner(t)
	plan := fixtureObject(t, "fixtures/plans/admitted-trial-plan-v1/valid/minimal.json")
	refs := object(plan["input_refs"])
	input := map[string]any{}
	for key, value := range refs {
		if value != nil {
			input[key] = value
		}
	}
	fragment, err := AdmitFragment(owner, TrialInputRefs, input, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	actual, err := json.Marshal(fragment.Document())
	if err != nil {
		t.Fatal(err)
	}
	refs["capture_spec_refs"] = []any{}
	expected, err := json.Marshal(refs)
	if err != nil {
		t.Fatal(err)
	}
	assertExperimentJSON(t, actual, expected)
}

type trialSealingReferenceCase struct {
	Path   string
	Result json.RawMessage
}

func checkTrialSealingReference(t *testing.T, c trialSealingReferenceCase, owner *Validator) {
	t.Helper()

	data, err := os.ReadFile("../../../../" + c.Path)
	if err != nil {
		t.Fatal(err)
	}
	var fields map[string]any
	if decodeExact(data, &fields) != nil {
		t.Fatal("invalid fixture")
	}
	delete(fields, "plan_digest")
	for _, entry := range object(fields["entries"]) {
		delete(object(entry), "entry_digest")
	}
	data, err = json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	sealed, err := SealTrialPlan(owner, data, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	actual, err := TrialPlanProjection(owner, sealed, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64})
	if err != nil {
		t.Fatal(err)
	}
	assertExperimentJSON(t, actual, c.Result)
	if _, err := TrialEntryOrder(owner, sealed); err != nil {
		t.Fatal(err)
	}
}
