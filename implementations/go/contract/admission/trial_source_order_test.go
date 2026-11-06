package admission

import "testing"

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
