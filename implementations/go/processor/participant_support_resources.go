package processor

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type resourceSupportPool struct {
	PoolRef              string                  `json:"pool_ref"`
	OwnerKind            string                  `json:"owner_kind"`
	OwnerRef             string                  `json:"owner_ref"`
	ResourceKind         participantResourceKind `json:"resource_kind"`
	Unit                 string                  `json:"unit"`
	AccountingMode       string                  `json:"accounting_mode"`
	MeterProfileRef      string                  `json:"meter_profile_ref"`
	Capacity             json.Number             `json:"capacity"`
	ProtectedCapacity    json.Number             `json:"protected_capacity"`
	FairnessPolicy       string                  `json:"fairness_policy"`
	PriorityClasses      []string                `json:"priority_classes"`
	Borrowing            string                  `json:"borrowing"`
	Reclaim              string                  `json:"reclaim"`
	MaxQueueTicks        json.Number             `json:"max_queue_ticks"`
	StarvationBoundTicks json.Number             `json:"starvation_bound_ticks"`
}
type resourceBudgetSupport struct {
	Context          *binding.DomainProfileResolutionContextV1 `json:"domain_profile_context"`
	Strength         string                                    `json:"support_strength"`
	OwnerKinds       []string                                  `json:"supported_owner_kinds"`
	ResourceKinds    []participantResourceKind                 `json:"supported_resource_kinds"`
	AccountingModes  []string                                  `json:"supported_accounting_modes"`
	ResetModes       []string                                  `json:"supported_reset_modes"`
	FairnessPolicies []string                                  `json:"supported_fairness_policies"`
	Contracts        []string                                  `json:"realization_contract_ids"`
	Pools            []resourceSupportPool                     `json:"configured_pools"`
}

func resourcePoolKey(pool resourceSupportPool) [7]string {
	return [7]string{pool.PoolRef, pool.OwnerKind, pool.OwnerRef, string(pool.ResourceKind), pool.Unit, pool.AccountingMode, pool.MeterProfileRef}
}
func participantResourceSupportGaps(manifest binding.BackendManifestV2, raw json.RawMessage, policies []*participantAutonomous) ([]string, error) {
	governed := []*participantAutonomous{}
	for _, policy := range policies {
		if policy.Profile == termParticipantAutonomousExecutionV3 {
			governed = append(governed, policy)
		}
	}
	if len(governed) == 0 {
		return []string{}, nil
	}
	if len(raw) == 0 || string(raw) == termNull {
		return []string{"participant-autonomous-execution/v3 requires resource-budget capabilities"}, nil
	}
	var caps resourceBudgetSupport
	if json.Unmarshal(raw, &caps) != nil {
		return nil, invalidCompiled()
	}
	state := newResourceSupportAssessment(caps, resourceCapabilityGaps(manifest, caps))
	for _, policy := range governed {
		if err := state.assessPolicy(policy); err != nil {
			return nil, err
		}
	}
	state.checkAggregate()
	return state.gaps, nil
}

type resourceSupportAssessment struct {
	caps                 resourceBudgetSupport
	pools                map[[7]string]resourceSupportPool
	aggregate, protected map[[7]string]*big.Int
	order                [][7]string
	gaps                 []string
}

func newResourceSupportAssessment(caps resourceBudgetSupport, gaps []string) resourceSupportAssessment {
	state := resourceSupportAssessment{caps: caps, pools: map[[7]string]resourceSupportPool{}, aggregate: map[[7]string]*big.Int{}, protected: map[[7]string]*big.Int{}, gaps: gaps}
	for _, pool := range caps.Pools {
		key := resourcePoolKey(pool)
		if _, exists := state.pools[key]; !exists {
			state.pools[key] = pool
		}
	}
	return state
}

func resourceCapabilityGaps(manifest binding.BackendManifestV2, caps resourceBudgetSupport) []string {
	gaps := []string{}
	if caps.Strength != "bounded" && caps.Strength != termExact {
		gaps = append(gaps, "participant resource budgets require bounded or exact support; backend declares "+caps.Strength)
	}
	if missing := missingStrings([]string{"participant-resource-budget-policy-v1", "participant-resource-pool-capacity-v1", "participant-resource-budget-state-v1", "participant-resource-budget-event-v1"}, fieldValue(manifest.SupportedContractVersions)); len(missing) > 0 {
		gaps = append(gaps, "participant resource budgets missing manifest contracts: "+strings.Join(missing, ", "))
	}
	if missing := missingStrings([]string{"participant-resource-budget-state-v1", "participant-resource-budget-event-v1"}, caps.Contracts); len(missing) > 0 {
		gaps = append(gaps, "participant resource budgets missing realization contracts: "+strings.Join(missing, ", "))
	}
	return gaps
}

func (state *resourceSupportAssessment) assessPolicy(policy *participantAutonomous) error {
	if !slices.Contains(state.caps.FairnessPolicies, policy.ResourceFairness.Policy) {
		state.gaps = append(state.gaps, "unsupported participant resource fairness policy: "+policy.ResourceFairness.Policy)
	}
	state.gaps = append(state.gaps, resourceParentGaps(policy)...)
	seen := map[[7]string]bool{}
	for _, demand := range policy.ResourceDemands {
		if err := state.assessDemand(policy, demand, seen); err != nil {
			return err
		}
	}
	return nil
}

func resourceParentGaps(policy *participantAutonomous) []string {
	gaps := []string{}
	demands := map[string]participantResourceDemand{}
	children := map[string]*big.Int{}
	parentOrder := []string{}
	for _, demand := range policy.ResourceDemands {
		demands[demand.BudgetID] = demand
		if demand.ParentBudgetRef != nil {
			parent := *demand.ParentBudgetRef
			if children[parent] == nil {
				children[parent] = new(big.Int)
				parentOrder = append(parentOrder, parent)
			}
			children[parent].Add(children[parent], exactInteger(demand.Limit))
		}
	}
	for _, parent := range parentOrder {
		demand, exists := demands[parent]
		if !exists || children[parent].Cmp(exactInteger(demand.Limit)) > 0 {
			gaps = append(gaps, "participant resource budget parent "+parent+" is missing or overcommitted by child limits")
		}
	}
	return gaps
}

func resourceUnsupportedAttributes(demand participantResourceDemand, caps resourceBudgetSupport) []string {
	unsupported := []string{}
	for _, field := range []struct {
		label, value string
		supported    bool
	}{
		{"owner kind", demand.OwnerKind, slices.Contains(caps.OwnerKinds, demand.OwnerKind)},
		{"resource kind", demand.ResourceKind.label(), slices.Contains(caps.ResourceKinds, demand.ResourceKind)},
		{"accounting mode", demand.AccountingMode, slices.Contains(caps.AccountingModes, demand.AccountingMode)},
		{"reset mode", demand.Reset, slices.Contains(caps.ResetModes, demand.Reset)},
	} {
		if !field.supported {
			unsupported = append(unsupported, field.label+" "+field.value)
		}
	}
	return unsupported
}

func (state *resourceSupportAssessment) assessDemand(policy *participantAutonomous, demand participantResourceDemand, seen map[[7]string]bool) error {
	supported, err := resourceDemandMeasureSupported(demand, state.caps.Context)
	if err != nil {
		return err
	}
	if !supported {
		state.gaps = append(state.gaps, participantResourceBudgetPrefix+demand.BudgetID+" lacks supported profile semantics")
		return nil
	}
	unsupported := resourceUnsupportedAttributes(demand, state.caps)
	if len(unsupported) > 0 {
		state.gaps = append(state.gaps, participantResourceBudgetPrefix+demand.BudgetID+" unsupported: "+strings.Join(unsupported, ", "))
		return nil
	}
	key := [7]string{demand.PoolRef, demand.OwnerKind, demand.OwnerAddress, string(demand.ResourceKind), demand.Unit, demand.AccountingMode, demand.MeterProfileRef}
	pool, exists := state.pools[key]
	if !exists {
		state.gaps = append(state.gaps, participantResourceBudgetPrefix+demand.BudgetID+" ("+demand.ResourceKind.label()+") has no exact configured owner/unit/accounting/meter capacity")
		return nil
	}
	if seen[key] {
		state.gaps = append(state.gaps, "participant policy "+policy.Address+" aliases canonical resource pool "+pool.PoolRef)
		return nil
	}
	seen[key] = true
	state.countDemand(key, demand, policy.ResourceFairness.Protected)
	state.gaps = append(state.gaps, resourcePoolPolicyGaps(demand, policy.ResourceFairness, pool)...)
	return nil
}

func (state *resourceSupportAssessment) countDemand(key [7]string, demand participantResourceDemand, protected bool) {
	if state.aggregate[key] == nil {
		state.aggregate[key] = new(big.Int)
		state.protected[key] = new(big.Int)
		state.order = append(state.order, key)
	}
	state.aggregate[key].Add(state.aggregate[key], exactInteger(demand.Limit))
	if protected {
		state.protected[key].Add(state.protected[key], exactInteger(demand.Limit))
	}
}

func resourcePoolPolicyGaps(demand participantResourceDemand, fairness participantResourceFairness, pool resourceSupportPool) []string {
	gaps := []string{}
	prefix := participantResourceBudgetPrefix + demand.BudgetID + " (" + demand.ResourceKind.label() + ")"
	if exactInteger(pool.Capacity).Cmp(exactInteger(demand.Limit)) < 0 {
		gaps = append(gaps, prefix+" requires capacity "+exactInteger(demand.Limit).String()+"; configured capacity is "+exactInteger(pool.Capacity).String())
	}
	if pool.FairnessPolicy != fairness.Policy {
		gaps = append(gaps, prefix+" requires fairness "+fairness.Policy+"; configured pool declares "+pool.FairnessPolicy)
	}
	if !slices.Contains(pool.PriorityClasses, fairness.PriorityClass) {
		gaps = append(gaps, prefix+" requires priority class "+fairness.PriorityClass)
	}
	if pool.Borrowing != fairness.Borrowing || pool.Reclaim != fairness.Reclaim {
		gaps = append(gaps, prefix+" fairness borrowing/reclaim does not match configured pool")
	}
	if exactInteger(pool.MaxQueueTicks).Cmp(exactInteger(fairness.MaxQueueTicks)) > 0 || exactInteger(pool.StarvationBoundTicks).Cmp(exactInteger(fairness.StarvationBoundTicks)) > 0 {
		gaps = append(gaps, prefix+" configured fairness queue/starvation bounds are weaker than required")
	}
	if fairness.Protected && exactInteger(pool.ProtectedCapacity).Cmp(exactInteger(demand.Reservation)) < 0 {
		gaps = append(gaps, prefix+" lacks protected capacity")
	}
	return gaps
}

func (state *resourceSupportAssessment) checkAggregate() {
	for _, key := range state.order {
		pool := state.pools[key]
		if state.aggregate[key].Cmp(exactInteger(pool.Capacity)) > 0 {
			state.gaps = append(state.gaps, "participant resource pool "+pool.PoolRef+" aggregate policy limits require "+state.aggregate[key].String()+"; configured capacity is "+exactInteger(pool.Capacity).String())
		}
		if state.protected[key].Cmp(exactInteger(pool.ProtectedCapacity)) > 0 {
			state.gaps = append(state.gaps, "participant resource pool "+pool.PoolRef+" protected policy limits require "+state.protected[key].String()+"; configured protected capacity is "+exactInteger(pool.ProtectedCapacity).String())
		}
	}
}

func resourceDemandMeasureSupported(demand participantResourceDemand, context *binding.DomainProfileResolutionContextV1) (bool, error) {
	if len(demand.ResourceKind) == 0 || demand.ResourceKind[0] != '{' {
		return true, nil
	}
	owner, err := processorAdmissionOwner()
	if err != nil {
		return false, err
	}
	raw, err := demand.ResourceKind.MarshalJSON()
	if err != nil {
		return false, err
	}
	var kind any
	if json.Unmarshal(raw, &kind) != nil {
		return false, invalidCompiled()
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, kind, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64})
	if err != nil {
		return false, err
	}
	return admission.ParticipantResourceMeasureSupported(owner, fragment, demand.Unit, demand.AccountingMode, demand.MeterProfileRef, demand.Reset, context)
}
