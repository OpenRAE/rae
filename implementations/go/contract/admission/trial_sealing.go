package admission

import (
	"bytes"
	"encoding/json"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

const trialPlanContract = "admitted-trial-plan-v1"

// SealTrialPlan constructs children before computing the enclosing digest.
// Digests establish integrity; the complete owner still checks all joins.
func SealTrialPlan(v *Validator, data []byte, limits ingress.Limits) (validation.Value, error) {
	if v == nil {
		return validation.Value{}, invalid()
	}
	parsed, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return validation.Value{}, err
	}
	root := object(parsed)
	order, err := trialSourceMemberOrder(string(data), pathTrialEntries)
	if err != nil {
		return validation.Value{}, err
	}
	placeholder := "sha256:" + strings.Repeat("0", 64)
	root["plan_digest"] = placeholder
	for _, entry := range object(root["entries"]) {
		if object(entry) == nil {
			return validation.Value{}, invalid()
		}
		object(entry)["entry_digest"] = placeholder
	}
	data, err = json.Marshal(root)
	if err != nil {
		return validation.Value{}, invalid()
	}
	root, err = v.trialConstructed(data, limits)
	if err != nil {
		return validation.Value{}, err
	}
	for _, entry := range object(root["entries"]) {
		content := object(entry)
		delete(content, "entry_digest")
		digest, checkErr := jsonDigest(content)
		if checkErr != nil {
			return validation.Value{}, checkErr
		}
		content["entry_digest"] = digest
	}
	delete(root, "plan_digest")
	digest, err := jsonDigest(root)
	if err != nil {
		return validation.Value{}, err
	}
	root["plan_digest"] = digest
	data, err = trialOrderedJSON(root, order)
	if err != nil || len(data) > limits.MaxBytes {
		return validation.Value{}, invalid()
	}
	return v.Validate(trialPlanContract, data, limits, nil)
}

// TrialPlanProjection returns the native constructor's serialization after
// rechecking the supplied handle with this owner.
func TrialPlanProjection(v *Validator, plan validation.Value, limits ingress.Limits) ([]byte, error) {
	if v == nil || plan.ContractID() != trialPlanContract {
		return nil, invalid()
	}
	if _, err := v.Validate(trialPlanContract, plan.JSON(), limits, nil); err != nil {
		return nil, err
	}
	root, err := v.trialConstructed(plan.JSON(), limits)
	if err != nil {
		return nil, err
	}
	order, err := trialSourceMemberOrder(string(plan.JSON()), pathTrialEntries)
	if err != nil {
		return nil, err
	}
	return trialOrderedJSON(root, order)
}

// TrialEntryOrder preserves source member order for equal coordinate keys.
// A recorded allocation is the admitted dispatch order when one exists.
func TrialEntryOrder(v *Validator, plan validation.Value) ([]string, error) {
	if v == nil || plan.ContractID() != trialPlanContract {
		return nil, invalid()
	}
	data := plan.JSON()
	limits := ingress.Limits{MaxBytes: max(32<<20, len(data)), MaxDepth: 64}
	if _, err := v.Validate(trialPlanContract, data, limits, nil); err != nil {
		return nil, err
	}
	parsed, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return nil, err
	}
	if allocation := at(parsed, "allocation"); allocation != nil {
		return stringsOf(at(allocation, "entry_order")), nil
	}
	order, err := trialSourceMemberOrder(string(data), pathTrialEntries)
	if err != nil {
		return nil, err
	}
	return trialCoordinateOrder(at(parsed, "entries"), order)
}

// trialConstructed defaults each collection member independently. The generic
// defaults walker has a per-value visit bound; it must not repeatedly copy a
// complete, potentially 32 MiB plan while validating every entry digest.
func (e *Validator) trialConstructed(data []byte, limits ingress.Limits) (map[string]any, error) {
	parsed, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return nil, err
	}
	root := object(parsed)
	models := map[string]string{"entries": modelAdmittedTrialEntry, "cleanup_plans": "TrialCleanupPlanModel", "stochastic_controls": "ExperimentStochasticControlModel"}
	header := trialConstructorHeader(root, models)
	raw, err := json.Marshal(header)
	if err != nil {
		return nil, invalid()
	}
	defaulted, err := e.low.Defaulted(trialPlanContract, raw, limits)
	if err != nil {
		return nil, err
	}
	result := object(defaulted)
	if err = e.trialConstructorMembers(root, result, models, limits); err != nil {
		return nil, err
	}
	// Bound the published model projection; omitted constructor defaults do
	// not consume the caller's allowance a second time during digest checks.
	trialProjection(result)
	raw, err = json.Marshal(result)
	if err != nil || len(raw) > limits.MaxBytes {
		return nil, invalid()
	}
	if err := e.experimentConstructorDefaults(trialPlanContract, raw, result, limits); err != nil {
		return nil, err
	}
	trialProjection(result)
	return result, nil
}

func trialConstructorHeader(root map[string]any, models map[string]string) map[string]any {
	header := maps.Clone(root)
	for field := range models {
		members := map[string]any{}
		for key, value := range object(root[field]) {
			members[key] = value
			break
		}
		if root[field] != nil {
			header[field] = members
		}
	}
	return header
}
func (e *Validator) trialConstructorMembers(root, result map[string]any, models map[string]string, limits ingress.Limits) error {
	for field, model := range models {
		members := map[string]any{}
		for key, value := range object(root[field]) {
			raw, err := json.Marshal(value)
			if err != nil {
				return invalid()
			}
			member, err := e.low.DefaultedObjectFragment(trialPlanContract, schemaDefinitionsPrefix+model, raw, limits)
			if err != nil {
				return err
			}
			members[key] = member
		}
		result[field] = members
	}
	return nil
}

func trialOrderedJSON(root map[string]any, order []string) ([]byte, error) {
	entries := object(root["entries"])
	if len(order) != len(entries) || !unique(order) {
		return nil, invalid()
	}
	var ordered bytes.Buffer
	ordered.WriteByte('{')
	for index, key := range order {
		entry, present := entries[key]
		if !present {
			return nil, invalid()
		}
		if index > 0 {
			ordered.WriteByte(',')
		}
		name, keyErr := json.Marshal(key)
		if keyErr != nil {
			return nil, invalid()
		}
		data, err := json.Marshal(entry)
		if err != nil {
			return nil, invalid()
		}
		ordered.Write(name)
		ordered.WriteByte(':')
		ordered.Write(data)
	}
	ordered.WriteByte('}')
	fields := make(map[string]json.RawMessage, len(root))
	for key, value := range root {
		data, err := json.Marshal(value)
		if err != nil {
			return nil, invalid()
		}
		fields[key] = data
	}
	fields["entries"] = ordered.Bytes()
	return json.Marshal(fields)
}

// TrialEntryRetainedBytes returns the canonical byte size of one sealed trial
// entry and its cleanup plan, as the admitted plan retains them. The compiler
// charges each retained entry before it seals the complete plan.
func TrialEntryRetainedBytes(v *Validator, entry, cleanup []byte) (int, error) {
	if v == nil || len(entry) > int(^uint(0)>>2) || len(cleanup) > int(^uint(0)>>2) {
		return 0, invalid()
	}
	limits := ingress.Limits{MaxBytes: max(32<<20, 2*(len(entry)+len(cleanup))), MaxDepth: 64}
	parsed, err := ingress.Parse(entry, limits, ingress.Object)
	if err != nil {
		return 0, err
	}
	// A sealed entry carries its digest; the placeholder has the same canonical size.
	object(parsed)["entry_digest"] = "sha256:" + strings.Repeat("0", 64)
	raw, err := json.Marshal(parsed)
	if err != nil {
		return 0, invalid()
	}
	projected, err := v.trialEntryProjection(trialPlanContract, raw, limits)
	if err != nil {
		return 0, err
	}
	if raw, err = json.Marshal(projected); err != nil {
		return 0, invalid()
	}
	entryBytes, err := canonjson.JCS(raw)
	if err != nil {
		return 0, invalid()
	}
	cleanupProjection, err := v.experimentProjection("trial-cleanup-plan-v1", cleanup)
	if err != nil {
		return 0, err
	}
	cleanupBytes, err := canonjson.JCS(cleanupProjection)
	if err != nil {
		return 0, invalid()
	}
	return len(entryBytes) + len(cleanupBytes), nil
}
