package admission

import (
	"encoding/json"
	"math/big"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

func resourcePoolIdentity(v any) (string, error) {
	values := []any{at(v, "pool_ref"), at(v, "owner_kind"), at(v, "owner_ref"), at(v, "resource_kind"), at(v, "unit"), at(v, "accounting_mode"), at(v, "meter_profile_ref")}
	encoded := make([]string, len(values))
	for index, value := range values {
		if index == 3 && object(value) != nil {
			// The incumbent ordered model serializer fixes this nested key order.
			fields := []string{termNamespace, termAuthority, termProfileID, termRevision, "definition_digest"}
			parts := make([]string, len(fields))
			for position, field := range fields {
				text, err := resourceIdentityJSON(at(value, field))
				if err != nil {
					return "", err
				}
				parts[position] = `"` + field + `":` + text
			}
			encoded[index] = "{" + strings.Join(parts, ",") + "}"
			continue
		}
		text, err := resourceIdentityJSON(value)
		if err != nil {
			return "", err
		}
		encoded[index] = text
	}
	return "participant-resource-pool:" + digest.SHA256([]byte("["+strings.Join(encoded, ",")+"]")), nil
}

func resourceIdentityJSON(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", invalid()
	}
	encoded, err := canonjson.Sorted(raw, true)
	if err != nil {
		return "", invalid()
	}
	return string(encoded), nil
}

func resourcePoolState(v any) error {
	if err := resourceQuantity(v); err != nil {
		return err
	}
	identity, err := resourcePoolIdentity(v)
	if err != nil || stringAt(v, "pool_state_ref") != identity || numericGreater(at(v, "protected_capacity"), at(v, "capacity")) {
		return invalid()
	}
	total := new(big.Rat)
	for key, allocation := range object(at(v, "allocations")) {
		if err := resourcePoolAllocation(v, key, allocation); err != nil {
			return err
		}
		field := "cumulative_use"
		if mode := stringAt(v, "accounting_mode"); mode == "reservable_gauge" || mode == "lease" {
			field = "current_use"
		}
		for _, counter := range []string{field, "reserved"} {
			amount, ok := number(at(allocation, counter))
			if !ok {
				return invalid()
			}
			total.Add(total, amount)
		}
	}
	capacity, ok := number(at(v, "capacity"))
	return require(ok && total.Cmp(capacity) <= 0)
}

func resourcePoolAllocation(pool any, key string, allocation any) error {
	if key != stringAt(allocation, "budget_state_ref") || !set(at(pool, "priority_classes"))[stringAt(allocation, "priority_class")] || !matchingFields(pool, allocation, "borrowing", "reclaim") {
		return invalid()
	}
	return require(!numericGreater(at(pool, "max_queue_ticks"), at(allocation, "max_queue_ticks")) && !numericGreater(at(pool, "starvation_bound_ticks"), at(allocation, "starvation_bound_ticks")))
}
