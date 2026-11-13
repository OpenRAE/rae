package processor

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"
)

func (state *compilerState) participantBudget(policy participantExecutionSource, participants []string) ([]participantResourceOwner, []participantResourceDemand, participantResourceFairness) {
	if policy.ResourceBudget == nil {
		if len(participants) == 0 {
			state.err = invalidCompiled()
			return nil, nil, participantResourceFairness{}
		}
		owner := participantResourceOwner{"legacy-participant", termParticipant, participants[0]}
		attempts := policy.MaxActionAttempts
		demands := []participantResourceDemand{
			{BudgetID: "legacy-action-rate", OwnerID: owner.OwnerID, OwnerKind: owner.Kind, OwnerAddress: owner.Address, PoolRef: owner.OwnerID, ResourceKind: "action_rate", Unit: "actions", AccountingMode: "windowed_counter", MeterProfileRef: "raes.action-attempt/v1", Limit: attempts, Reservation: "1", Reset: "time_segment", WindowTicks: &attempts, EvidenceRefs: []string{}, Provenance: "legacy_maximum"},
			{BudgetID: "legacy-concurrent-actions", OwnerID: owner.OwnerID, OwnerKind: owner.Kind, OwnerAddress: owner.Address, PoolRef: owner.OwnerID, ResourceKind: "concurrent_actions", Unit: "actions", AccountingMode: "reservable_gauge", MeterProfileRef: "raes.concurrent-action/v1", Limit: policy.MaxInFlight, Reservation: "1", Reset: "reconciled", EvidenceRefs: []string{}, Provenance: "legacy_maximum"},
		}
		return []participantResourceOwner{owner}, demands, participantResourceFairness{Policy: "legacy_bounded", PriorityClass: "standard", Weight: "1", Borrowing: termNone, Reclaim: termNone, MaxQueueTicks: "0", StarvationBoundTicks: "1"}
	}
	source := policy.ResourceBudget
	owners := []participantResourceOwner{}
	byID := map[string]participantResourceOwner{}
	for _, id := range slices.Sorted(maps.Keys(source.Owners)) {
		input := source.Owners[id]
		owner := participantResourceOwner{id, input.Kind, state.participantOwnerAddress(input, participants)}
		owners = append(owners, owner)
		byID[id] = owner
	}
	demands := []participantResourceDemand{}
	for _, id := range slices.Sorted(maps.Keys(source.Dimensions)) {
		input := source.Dimensions[id]
		owner, exists := byID[input.OwnerRef]
		if !exists {
			state.err = invalidCompiled()
			return nil, nil, participantResourceFairness{}
		}
		demands = append(demands, participantResourceDemand{BudgetID: id, OwnerID: owner.OwnerID, OwnerKind: owner.Kind, OwnerAddress: owner.Address, PoolRef: input.PoolRef, ResourceKind: input.ResourceKind, Unit: input.Unit, AccountingMode: input.AccountingMode, MeterProfileRef: input.MeterProfileRef, Limit: input.Limit, Reservation: input.Reservation, Reset: input.Reset, WindowTicks: input.WindowTicks, ParentBudgetRef: input.ParentBudgetRef, EvidenceRefs: nonNilStrings(input.EvidenceRefs), Provenance: "authored"})
	}
	return owners, demands, source.Fairness
}

func (state *compilerState) participantOwnerAddress(owner participantBudgetOwner, participants []string) string {
	switch owner.Kind {
	case termParticipant:
		found := ""
		for _, address := range participants {
			if strings.HasSuffix(address, "."+owner.Ref) {
				if found != "" {
					state.err = invalidCompiled()
					return ""
				}
				found = address
			}
		}
		if found == "" {
			state.err = invalidCompiled()
		}
		return found
	case "deployment_tenant":
		return state.address("deployment", "tenant", state.sectionName(owner.Ref, "deployment_tenants"))
	case "shared_service":
		refs := state.runtimeAddressesFor([]string{owner.Ref}, "operating-scope")
		if len(refs) != 1 || !strings.Contains(refs[0], ".service.") {
			state.err = invalidCompiled()
			return ""
		}
		return refs[0]
	default:
		return owner.Ref
	}
}

func numberDefault(value json.Number, fallback string) json.Number {
	if value == "" {
		return json.Number(fallback)
	}
	return value
}
