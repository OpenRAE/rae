package trial

import (
	"encoding/json"
	"errors"
	"maps"
	"math/big"
	"slices"
	"sort"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/fault"

	"github.com/OpenRAE/rae/implementations/go/internal/base/randstream"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func coordinates(spec experimentSpec, limits Limits) ([]coordinate, error) {
	conditions := []string{""}
	count := spec.RunPlan.Count
	if allocation := spec.RunPlan.Allocation; allocation != nil {
		conditions = slices.Clone(allocation.Conditions)
		slices.Sort(conditions)
		count = allocation.PerCondition
	}
	if count <= 0 || len(conditions) == 0 {
		return nil, refuse("coordinate-set-empty", "/run_plan", "run allocation produced no logical trial coordinates")
	}
	if count > limits.MaxCoordinates/len(conditions) {
		return nil, refuse("coordinate-limit-exceeded", "/run_plan", "logical trial coordinates exceed the compilation limit")
	}
	if !isNull(spec.Factorial) && len(conditions) > limits.MaxProductOutputs {
		return nil, refuse("product-limit-exceeded", "/factorial_design", "factorial conditions exceed the compilation limit")
	}
	result := make([]coordinate, 0, count*len(conditions))
	for _, condition := range conditions {
		for ordinal := 1; ordinal <= count; ordinal++ {
			replicate := "replicate-" + fmtReplicate(ordinal)
			c := coordinate{ReplicateID: &replicate}
			if condition != "" {
				c.ConditionID = &condition
			}
			result = append(result, c)
		}
	}
	return result, nil
}
func fmtReplicate(ordinal int) string {
	s := strconv.Itoa(ordinal)
	for len(s) < 6 {
		s = "0" + s
	}
	return s
}

func mergeSelections(a, b []selectionRecord) ([]selectionRecord, error) {
	result := slices.Clone(a)
	seen := map[string]bool{}
	for _, selection := range result {
		seen[selection.Point] = true
	}
	for _, selection := range b {
		if seen[selection.Point] {
			return nil, refuse("selection-point-duplicate", "/run_plan/selection_policies", "selection policies select one variation point more than once")
		}
		seen[selection.Point] = true
		result = append(result, selection)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Point < result[j].Point })
	return result, nil
}
func policySelection(policy selectionPolicy, outcome selectionOutcome) selectionRecord {
	return selectionRecord{Point: policy.Point, Policy: policy.ID, Kind: policy.Kind, Outcome: outcome}
}

func domainOutcomes(request Request, point string) ([]selectionOutcome, error) {
	fragments, err := sdl.VariationOutcomes(request.Family, point, request.Limits.MaxDomainValuesPerPoint)
	if err != nil {
		return nil, domainRefusal(err)
	}
	result := make([]selectionOutcome, len(fragments))
	for index, fragment := range fragments {
		raw, err := encoded(fragment.Document())
		if err != nil {
			return nil, err
		}
		if decode(raw, &result[index]) != nil {
			return nil, trialInvalid()
		}
	}
	return result, nil
}
func domainRefusal(err error) error {
	owned, ok := errors.AsType[*fault.Error](err)
	if !ok {
		return err
	}
	const address = "/family/variation_points"
	switch owned.Code() {
	case "trial-domain-limit-exceeded":
		return refuse("domain-limit-exceeded", address, "a variation-point domain exceeds the compilation limit")
	case "trial-domain-empty":
		return refuse("domain-empty", address, "a selected variation-point domain is empty")
	case "trial-domain-not-finite":
		return refuse("domain-not-finite", address, "trial-compiler-v1 admits only finite scalar domains")
	case "trial-domain-kind-unsupported":
		return refuse("domain-kind-unsupported", address, "the selected policy does not support this variation-point kind")
	default:
		return err
	}
}
func staticRows(request Request, spec experimentSpec, id string, active map[string]bool) ([][]selectionRecord, error) {
	if active[id] {
		return nil, trialInvalid()
	}
	active[id] = true
	defer delete(active, id)
	policy, exists := spec.RunPlan.Policies[id]
	if !exists {
		return nil, trialInvalid()
	}
	switch policy.Kind {
	case policyFixed:
		return [][]selectionRecord{{policySelection(policy, policy.Outcome)}}, nil
	case "enumerate":
		outcomes, err := domainOutcomes(request, policy.Point)
		if err != nil {
			return nil, err
		}
		rows := make([][]selectionRecord, len(outcomes))
		for index, outcome := range outcomes {
			rows[index] = []selectionRecord{policySelection(policy, outcome)}
		}
		return rows, nil
	case "product":
		return productRows(request, spec, policy, active)
	default:
		return nil, refuse("product-child-unsupported", "/run_plan/selection_policies/"+id, "product dimensions admit only fixed, enumerate, or nested product policies in v1")
	}
}
func productRows(request Request, spec experimentSpec, policy selectionPolicy, active map[string]bool) ([][]selectionRecord, error) {
	children := slices.Clone(policy.Refs)
	slices.Sort(children)
	result := [][]selectionRecord{{}}
	for _, id := range children {
		rows, err := staticRows(request, spec, id, active)
		if err != nil {
			return nil, err
		}
		if len(rows) > request.Limits.MaxProductOutputs/len(result) {
			return nil, refuse("product-limit-exceeded", "/run_plan/selection_policies/"+policy.ID, "selection product exceeds the compilation limit")
		}
		next, err := crossSelectionRows(result, rows)
		if err != nil {
			return nil, err
		}
		result = next
	}
	if len(result) != policy.Bound {
		return nil, refuse("policy-cardinality-mismatch", "/run_plan/selection_policies/"+policy.ID, "selection policy output cardinality does not match its declared bound")
	}
	return result, nil
}
func crossSelectionRows(result, rows [][]selectionRecord) ([][]selectionRecord, error) {
	next := make([][]selectionRecord, 0, len(rows)*len(result))
	for _, previous := range result {
		for _, row := range rows {
			merged, err := mergeSelections(previous, row)
			if err != nil {
				return nil, err
			}
			next = append(next, merged)
		}
	}
	return next, nil
}
func selectionRows(request Request, spec experimentSpec, coordinates []coordinate, points map[string]json.RawMessage) ([]selectionRow, error) {
	if !isNull(spec.Factorial) {
		return factorialRows(request, spec, coordinates, points)
	}
	fixed, nonfixed, err := selectionPolicyRoots(spec)
	if err != nil {
		return nil, err
	}
	rows := make([]selectionRow, len(coordinates))
	for index := range rows {
		rows[index] = selectionRow{selections: []selectionRecord{}, draws: []json.RawMessage{}}
	}
	if len(nonfixed) == 1 {
		rows, err = coordinatePolicyRows(request, spec, nonfixed[0], coordinates)
		if err != nil {
			return nil, err
		}
	}
	for index := range rows {
		merged, err := mergeSelections(rows[index].selections, fixed)
		if err != nil {
			return nil, err
		}
		if err = selectionPointsCovered(merged, points); err != nil {
			return nil, err
		}
		rows[index].selections = merged
	}
	return rows, nil
}
func selectionPointsCovered(merged []selectionRecord, points map[string]json.RawMessage) error {
	if len(merged) != len(points) {
		return refuse("variation-points-uncovered", "/run_plan/selection_policies", "every family variation point must be selected exactly once")
	}
	for _, selection := range merged {
		if _, present := points[selection.Point]; !present {
			return trialInvalid()
		}
	}
	return nil
}
func coordinatePolicyRows(request Request, spec experimentSpec, id string, coordinates []coordinate) ([]selectionRow, error) {
	policy := spec.RunPlan.Policies[id]
	var err error
	rows := make([]selectionRow, len(coordinates))
	for index := range rows {
		rows[index] = selectionRow{selections: []selectionRecord{}, draws: []json.RawMessage{}}
	}
	switch policy.Kind {
	case "sample":
		rows, err = sampleRows(request, spec, policy, coordinates)
	case policyStratified:
		rows, err = stratifiedRows(policy, coordinates)
	default:
		var static [][]selectionRecord
		static, err = staticRows(request, spec, policy.ID, map[string]bool{})
		if err == nil && len(static) != len(rows) {
			err = refuse("policy-cardinality-mismatch", "/run_plan/selection_policies/"+policy.ID, "selection policy output does not exactly cover the logical coordinates")
		}
		if err == nil {
			for index := range rows {
				rows[index].selections = static[index]
			}
		}
	}
	return rows, err
}
func selectionPolicyRoots(spec experimentSpec) ([]selectionRecord, []string, error) {
	referenced := map[string]bool{}
	for _, policy := range spec.RunPlan.Policies {
		if policy.Kind == "product" {
			for _, id := range policy.Refs {
				referenced[id] = true
			}
		}
	}
	fixed := []selectionRecord{}
	nonfixed := []string{}
	for _, id := range slices.Sorted(maps.Keys(spec.RunPlan.Policies)) {
		if referenced[id] {
			continue
		}
		policy := spec.RunPlan.Policies[id]
		if policy.Kind == policyFixed {
			fixed = append(fixed, policySelection(policy, policy.Outcome))
		} else {
			nonfixed = append(nonfixed, id)
		}
	}
	if len(nonfixed) > 1 {
		return nil, nil, refuse("policy-roots-ambiguous", "/run_plan/selection_policies", "multiple non-fixed selection policy roots are ambiguous")
	}
	return fixed, nonfixed, nil
}
func stratifiedRows(policy selectionPolicy, coordinates []coordinate) ([]selectionRow, error) {
	counts := map[string]int{}
	rows := make([]selectionRow, len(coordinates))
	for index, c := range coordinates {
		stratum, exists := policy.Strata[text(c.ConditionID)]
		if !exists {
			return nil, refuse("stratum-coordinate-missing", "/run_plan/selection_policies/"+policy.ID, "a stratified policy does not cover a logical trial coordinate")
		}
		counts[stratum.ID]++
		rows[index] = selectionRow{selections: []selectionRecord{policySelection(policy, policy.Outcomes[stratum.Outcome])}, draws: []json.RawMessage{}}
	}
	for id, stratum := range policy.Strata {
		if counts[id] != stratum.Count {
			return nil, refuse("stratum-cardinality-mismatch", "/run_plan/selection_policies/"+policy.ID, "stratified output counts do not match the logical coordinate allocation")
		}
	}
	return rows, nil
}

type drawAddress struct {
	Namespace  string     `json:"namespace"`
	Coordinate coordinate `json:"trial_coordinate"`
	Policy     string     `json:"selection_policy_id"`
	Point      string     `json:"variation_point_id"`
	Purpose    string     `json:"draw_purpose"`
	Local      int        `json:"local_coordinate"`
}
type drawRecord struct {
	Control   string      `json:"control_id"`
	Address   drawAddress `json:"address"`
	Transform string      `json:"transform_id"`
	Version   string      `json:"transform_version"`
	Local     int         `json:"local_coordinate"`
	Outcome   struct {
		Kind  string `json:"kind"`
		Value string `json:"value"`
	} `json:"outcome"`
	Attempts  int  `json:"rejection_attempts"`
	Exhausted bool `json:"rejection_exhausted"`
}

func sampleKey(spec experimentSpec, policy selectionPolicy) (stochasticControl, randstream.Key, error) {
	var control stochasticControl
	for _, raw := range spec.RunPlan.Controls {
		var candidate stochasticControl
		if decode(raw, &candidate) != nil {
			return control, randstream.Key{}, trialInvalid()
		}
		if candidate.ID == policy.Control {
			control = candidate
			break
		}
	}
	if control.Executable == nil {
		return control, randstream.Key{}, refuse("sample-control-unresolved", "/run_plan/selection_policies/"+policy.ID, "sample policy control is not executable")
	}
	binding := control.Executable
	if binding.Profile.ID != "blake3-xof-v1" || text(binding.Profile.Version) != "random-stream-profile/v1" {
		return control, randstream.Key{}, refuse("sample-profile-mismatch", "/run_plan/stochastic_controls/"+control.ID, "sample policy random-stream profile does not match trial-compiler-v1")
	}
	if binding.Entropy.Kind != "public-seed" {
		return control, randstream.Key{}, refuse("governed-entropy-resolver-required", "/run_plan/stochastic_controls/"+control.ID, "governed entropy requires an authorized in-process resolver")
	}
	seed, err := randstream.PublicSeed(binding.Entropy.Encoding, binding.Entropy.Value)
	if err != nil {
		return control, randstream.Key{}, err
	}
	key, err := randstream.DeriveKey(binding.Profile.ID, seed)
	return control, key, err
}
func sampleRows(request Request, spec experimentSpec, policy selectionPolicy, coordinates []coordinate) ([]selectionRow, error) {
	control, key, err := sampleKey(spec, policy)
	if err != nil {
		return nil, err
	}
	outcomes, err := domainOutcomes(request, policy.Point)
	if err != nil {
		return nil, err
	}
	rows := make([]selectionRow, len(coordinates))
	seen := map[string]bool{}
	for index, c := range coordinates {
		address := drawAddress{Namespace: control.Executable.Namespace, Coordinate: c, Policy: policy.ID, Point: policy.Point, Purpose: "sampling-selection"}
		// Stream bytes omit absent coordinate dimensions; archival draw records
		// retain their model's explicit null fields.
		raw, err := canonical(struct {
			Namespace  string `json:"namespace"`
			Coordinate any    `json:"trial_coordinate"`
			Policy     string `json:"selection_policy_id"`
			Point      string `json:"variation_point_id"`
			Purpose    string `json:"draw_purpose"`
			Local      int    `json:"local_coordinate"`
		}{address.Namespace, c.projection(), address.Policy, address.Point, address.Purpose, address.Local})
		if err != nil {
			return nil, err
		}
		if seen[string(raw)] {
			return nil, refuse("sample-address-collision", "/run_plan/selection_policies/"+policy.ID, "sample policy draw addresses are not unique")
		}
		seen[string(raw)] = true
		draw, err := randstream.BoundedInt(key, raw, 0, big.NewInt(0), big.NewInt(int64(len(outcomes)-1)), 32)
		if err != nil {
			return nil, err
		}
		if draw.Exhausted {
			return nil, refuse("sample-rejection-exhausted", "/run_plan/selection_policies/"+policy.ID, "sample policy exhausted its bounded transform")
		}
		record := drawRecord{Control: control.ID, Address: address, Transform: "bounded-integer", Version: "1", Attempts: draw.Attempts}
		record.Outcome.Kind = "public-value"
		record.Outcome.Value = draw.Value.String()
		raw, err = encoded(record)
		if err != nil {
			return nil, err
		}
		rows[index] = selectionRow{selections: []selectionRecord{policySelection(policy, outcomes[draw.Value.Int64()])}, draws: []json.RawMessage{raw}}
	}
	return rows, nil
}
