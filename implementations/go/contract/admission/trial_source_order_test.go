package admission

import (
	"compress/gzip"
	"io"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func TestTrialCoordinateTiesKeepOriginalSourceOrder(t *testing.T) {
	for _, test := range []struct {
		source, path string
		want         []string
	}{
		{`{"entries":{"z":{"coordinate":{"condition_id":"a","block_id":"first","replicate_id":"replicate-000001"}},"a":{"coordinate":{"condition_id":"a","block_id":"second","replicate_id":"replicate-000001"}}}}`, "", []string{"z", "a"}},
		{`{"nested":[{"p/~":{"entries":{"a":{"coordinate":{"condition_id":"a","block_id":"second","replicate_id":"replicate-000001"}},"z":{"coordinate":{"condition_id":"a","block_id":"first","replicate_id":"replicate-000001"}}}}}]}`, "/nested/0/p~1~0", []string{"a", "z"}},
	} {
		root := decodeRuleObject(t, test.source)
		plan, present := pointerAt(root, test.path)
		if !present {
			t.Fatal("missing fixture")
		}
		members, err := trialSourceMemberOrder(test.source, test.path+"/entries")
		if err != nil {
			t.Fatal(err)
		}
		order, err := trialCoordinateOrder(at(plan, "entries"), members)
		if err != nil {
			t.Fatal(err)
		}
		if !equal(order, test.want) {
			t.Errorf("order=%v want %v", order, test.want)
		}
	}
}

func TestTrialSourceOrderAcceptsBoundedLargeValueSet(t *testing.T) {
	file, err := os.Open("testdata/large-source-plan.json.gz")
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
	value, err := owner.Validate(trialPlanContract, raw, ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}, nil)
	if err != nil {
		t.Fatal("independently sealed 800-entry plan refused", err)
	}
	order, err := TrialEntryOrder(owner, value)
	if err != nil || len(order) != 800 {
		t.Fatal("large source order refused", err, len(order))
	}
}
