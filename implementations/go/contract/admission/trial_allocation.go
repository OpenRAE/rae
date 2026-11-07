package admission

import (
	"encoding/json"
	"math/big"
	"sort"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/base/randstream"
)

func pointerAt(root any, path string) (any, bool) {
	value := root
	for _, token := range jsonpointer.Tokens(path) {
		switch node := value.(type) {
		case map[string]any:
			var exists bool
			value, exists = node[token]
			if !exists {
				return nil, false
			}
		case []any:
			index, exists := jsonpointer.ArrayIndex(token, len(node))
			if !exists {
				return nil, false
			}
			value = node[index]
		default:
			return nil, false
		}
	}
	return value, true
}

func trialAllocation(plan any, source, path string) error {
	allocation := at(plan, "allocation")
	profile := stringAt(plan, "profiles", "allocation_profile")
	if (profile != "" && profile != postureNone) != (allocation != nil) {
		return invalid()
	}
	if allocation == nil {
		return nil
	}
	if !strings.Contains(stringAt(plan, "profiles", "compiler_profile"), "designed") {
		return invalid()
	}
	policy := at(allocation, termPolicy)
	control := at(plan, "stochastic_controls", stringAt(policy, "stochastic_control_ref"))
	binding := at(control, "executable_binding")
	if stringAt(control, "role") != "randomization" || stringAt(binding, "profile_ref", "ref_id") != termBlake3XofV1 || stringAt(binding, "profile_ref", "ref_version") != "random-stream-profile/v1" || stringAt(binding, "root_entropy", termKind) != "public-seed" {
		return invalid()
	}
	seed, err := randstream.PublicSeed(stringAt(binding, "root_entropy", "encoding"), stringAt(binding, "root_entropy", "value"))
	if err != nil {
		return invalid()
	}
	key, err := randstream.DeriveKey(termBlake3XofV1, seed)
	if err != nil {
		return invalid()
	}
	return trialAllocationDraws(plan, allocation, policy, binding, key, source, path)
}

type orderedTrial struct {
	id, condition string
	ordinal       int
}

func trialCoordinateOrder(entries any, sourceOrder []string) ([]string, error) {
	rows := make([]orderedTrial, 0, len(object(entries)))
	// Python sorts the source JSON member order stably when coordinates tie.
	// Distinct coordinates can differ only by block; no map iteration may decide authority.
	if len(sourceOrder) != len(object(entries)) || !unique(sourceOrder) {
		return nil, invalid()
	}
	for _, id := range sourceOrder {
		entry, present := object(entries)[id]
		if !present {
			return nil, invalid()
		}
		ordinal, err := trialReplicateOrdinal(entry)
		if err != nil {
			return nil, err
		}
		rows = append(rows, orderedTrial{id: id, condition: stringAt(entry, "coordinate", "condition_id"), ordinal: ordinal})
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if rows[i].condition != rows[j].condition {
			return rows[i].condition < rows[j].condition
		}
		if rows[i].ordinal != rows[j].ordinal {
			return rows[i].ordinal < rows[j].ordinal
		}
		return false
	})
	order := make([]string, len(rows))
	for index, row := range rows {
		order[index] = row.id
	}
	return order, nil
}

func trialAllocationDraws(plan, allocation, policy, binding any, key randstream.Key, source, path string) error {
	sourceOrder, err := trialSourceMemberOrder(source, path+"/entries")
	if err != nil {
		return err
	}
	order, err := trialCoordinateOrder(at(plan, "entries"), sourceOrder)
	if err != nil {
		return err
	}
	draws := array(at(allocation, "draws"))
	if len(draws) != len(order)-1 {
		return invalid()
	}
	for slot, index := 0, len(order)-1; index > 0; slot, index = slot+1, index-1 {
		address := map[string]any{"address_profile": "allocation-address-v1", termNamespace: at(binding, termNamespace), "allocation_policy_id": at(policy, "policy_id"), "draw_purpose": "condition-assignment", "slot": json.Number(strconv.Itoa(slot)), "local_coordinate": jsonZero}
		encoded, err := json.Marshal(address)
		if err != nil {
			return invalid()
		}
		canonical, err := canonjson.JCS(encoded)
		if err != nil {
			return invalid()
		}
		draw, err := randstream.BoundedInt(key, canonical, 0, big.NewInt(0), big.NewInt(int64(index)), 32)
		if err != nil || draw.Exhausted || !equal(at(draws[slot], "address"), address) || !countEqual(at(draws[slot], "value"), int(draw.Value.Int64())) || !countEqual(at(draws[slot], "rejection_attempts"), draw.Attempts) {
			return invalid()
		}
		selected := int(draw.Value.Int64())
		order[index], order[selected] = order[selected], order[index]
	}
	return require(equal(stringsOf(at(allocation, "entry_order")), order))
}

func trialReplicateOrdinal(entry any) (int, error) {
	ordinal := 0
	if replicate := at(entry, "coordinate", "replicate_id"); replicate != nil {
		value := strings.TrimPrefix(text(replicate), "replicate-")
		parsed, err := strconv.Atoi(value)
		if err != nil || len(value) != 6 || !strings.HasPrefix(text(replicate), "replicate-") {
			return 0, invalid()
		}
		ordinal = parsed
	}
	return ordinal, nil
}
