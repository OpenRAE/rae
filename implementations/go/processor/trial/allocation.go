package trial

import (
	"encoding/json"
	"math/big"
	"sort"

	"github.com/OpenRAE/rae/implementations/go/internal/base/randstream"
)

type allocationPolicy struct {
	ID      string `json:"policy_id"`
	Control string `json:"stochastic_control_ref"`
}
type allocationAddress struct {
	Profile   string `json:"address_profile"`
	Namespace string `json:"namespace"`
	PolicyID  string `json:"allocation_policy_id"`
	Purpose   string `json:"draw_purpose"`
	Slot      int    `json:"slot"`
	Local     int    `json:"local_coordinate"`
}
type allocationDraw struct {
	Address  allocationAddress `json:"address"`
	Value    int               `json:"value"`
	Attempts int               `json:"rejection_attempts"`
}

func compileAllocation(spec experimentSpec, plan *trialPlan) error {
	if isNull(spec.RunPlan.AllocationPolicy) {
		return nil
	}
	var policy allocationPolicy
	if decode(spec.RunPlan.AllocationPolicy, &policy) != nil {
		return trialInvalid()
	}
	control, key, err := sampleKey(spec, selectionPolicy{ID: policy.ID, Control: policy.Control})
	if err != nil {
		return err
	}
	for _, raw := range spec.RunPlan.Controls {
		var candidate stochasticControl
		if decode(raw, &candidate) != nil {
			return trialInvalid()
		}
		if candidate.ID == policy.Control {
			plan.Controls[policy.Control] = raw
			break
		}
	}
	entries := make([]trialEntry, 0, len(plan.Entries))
	for _, entry := range plan.Entries {
		entries = append(entries, entry)
	}
	sort.SliceStable(entries, func(i, j int) bool {
		a, b := entries[i].Coordinate, entries[j].Coordinate
		if text(a.ConditionID) != text(b.ConditionID) {
			return text(a.ConditionID) < text(b.ConditionID)
		}
		return text(a.ReplicateID) < text(b.ReplicateID)
	})
	order := make([]string, len(entries))
	for index, entry := range entries {
		order[index] = entry.ID
	}
	draws, err := shuffleAllocation(order, control, policy, key)
	if err != nil {
		return err
	}
	plan.Allocation, err = encoded(struct {
		Policy json.RawMessage  `json:"policy"`
		Order  []string         `json:"entry_order"`
		Draws  []allocationDraw `json:"draws"`
	}{spec.RunPlan.AllocationPolicy, order, draws})
	return err
}

func shuffleAllocation(order []string, control stochasticControl, policy allocationPolicy, key randstream.Key) ([]allocationDraw, error) {
	draws := []allocationDraw{}
	for slot, index := 0, len(order)-1; index > 0; slot, index = slot+1, index-1 {
		address := allocationAddress{"allocation-address-v1", control.Executable.Namespace, policy.ID, "condition-assignment", slot, 0}
		raw, checkErr := canonical(address)
		if checkErr != nil {
			return nil, checkErr
		}
		draw, checkErr := randstream.BoundedInt(key, raw, 0, big.NewInt(0), big.NewInt(int64(index)), 32)
		if checkErr != nil {
			return nil, checkErr
		}
		if draw.Exhausted {
			return nil, trialInvalid()
		}
		selected := int(draw.Value.Int64())
		order[index], order[selected] = order[selected], order[index]
		draws = append(draws, allocationDraw{address, selected, draw.Attempts})
	}
	return draws, nil
}
