package processor

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/pyrepr"
)

type participantConditionDeclaration struct {
	ID, Class                 string
	SupportRefs, EvidenceRefs []string
}
type participantEffectDeclaration struct {
	ID, Class                string
	TargetRefs, EvidenceRefs []string
}
type participantResultPrecondition struct {
	ID           string   `json:"precondition_id"`
	Class        string   `json:"precondition_class"`
	Status       string   `json:"status"`
	Participant  string   `json:"participant_address"`
	Episode      string   `json:"episode_id"`
	Action       string   `json:"action_contract_address"`
	Point        string   `json:"observation_point"`
	SupportRefs  []string `json:"support_refs"`
	EvidenceRefs []string `json:"evidence_refs"`
	Diagnostics  []string `json:"diagnostics"`
}
type participantResultEffect struct {
	ID           string   `json:"effect_id"`
	Class        string   `json:"effect_class"`
	Description  string   `json:"description"`
	TargetRefs   []string `json:"target_refs"`
	EvidenceRefs []string `json:"evidence_refs"`
	Diagnostics  []string `json:"diagnostics"`
}
type participantActionResult struct {
	Status               string                          `json:"status"`
	Participant          string                          `json:"participant_address"`
	Episode              string                          `json:"episode_id"`
	Instance             string                          `json:"action_instance_id"`
	Action               string                          `json:"action_contract_address"`
	Point                string                          `json:"observation_point"`
	Preconditions        []participantResultPrecondition `json:"preconditions"`
	Effects              []participantResultEffect       `json:"effects"`
	Failure              *string                         `json:"failure_class"`
	Observations         []string                        `json:"observations"`
	EvidenceRefs         []string                        `json:"evidence_refs"`
	Diagnostics          []string                        `json:"diagnostics"`
	TemporalEvidence     []json.RawMessage               `json:"temporal_evidence"`
	ResourceMeasurements []struct {
		BudgetStateRef string `json:"budget_state_ref"`
	} `json:"resource_measurements"`
}
type participantViolations struct {
	messages []string
	work     participantWork
	bytes    int
	err      error
}

func newParticipantViolations() *participantViolations {
	return &participantViolations{messages: []string{}, work: participantWork{remaining: participantRelationWork}, bytes: 8 << 20}
}
func (violations *participantViolations) add(message string) {
	if violations.err != nil {
		return
	}
	if !violations.work.spend(1) || len(message) > violations.bytes {
		violations.err = participantContractInput()
		return
	}
	violations.bytes -= len(message)
	violations.messages = append(violations.messages, message)
}
func (violations *participantViolations) difference(left, right []string) []string {
	if !violations.spend(len(left) + len(right)) {
		return nil
	}
	return participantStringDifference(left, right)
}
func (violations *participantViolations) spend(count int) bool {
	if violations.err != nil {
		return false
	}
	if !violations.work.spend(count) {
		violations.err = participantContractInput()
		return false
	}
	return true
}
func (result participantActionResult) locallyValid() bool {
	if result.Participant == "" || result.Episode == "" || result.Instance == "" || !strings.HasPrefix(result.Action, "participant.action-contract.") || !participantObservationPoint(result.Point, result.Instance) || len(result.Preconditions) == 0 {
		return false
	}
	if !participantUniqueStrings(result.Observations) || !participantUniqueStrings(result.EvidenceRefs) || !participantUniqueStrings(result.Diagnostics) {
		return false
	}
	if !result.preconditionsValid() || !result.effectsValid() {
		return false
	}
	return result.resourceMeasurementsValid() && result.failureStateValid()
}
func (result participantActionResult) resourceMeasurementsValid() bool {
	ids := map[string]bool{}
	for _, measurement := range result.ResourceMeasurements {
		if measurement.BudgetStateRef == "" || ids[measurement.BudgetStateRef] {
			return false
		}
		ids[measurement.BudgetStateRef] = true
	}
	return true
}
func (result participantActionResult) failureStateValid() bool {
	if !result.blockedPreconditionsValid() {
		return false
	}
	if (result.Status == termSucceeded || result.Status == termAccepted) && result.Failure != nil {
		return false
	}
	if (result.Status == termSucceeded || result.Status == termPartialSuccess) && len(result.Effects) == 0 {
		return false
	}
	return !slices.Contains([]string{"rejected", "withheld", termFailed, termPartialSuccess, termUnknown}, result.Status) || result.Failure != nil
}
func (result participantActionResult) blockedPreconditionsValid() bool {
	success := slices.Contains([]string{termAccepted, termSucceeded, termPartialSuccess}, result.Status)
	for _, precondition := range result.Preconditions {
		if precondition.Status == "unsatisfied" || precondition.Status == "unresolved" {
			if success || result.Failure == nil {
				return false
			}
		}
	}
	return true
}
func participantObservationPoint(point, instance string) bool {
	return instance != "" && slices.Contains(strings.Split(point, ":"), instance)
}
func (result participantActionResult) preconditionsValid() bool {
	ids := map[string]bool{}
	for _, item := range result.Preconditions {
		if item.ID == "" || ids[item.ID] || item.Participant != result.Participant || item.Episode != result.Episode || item.Action != result.Action || !participantObservationPoint(item.Point, result.Instance) {
			return false
		}
		ids[item.ID] = true
		if !participantUniqueStrings(item.SupportRefs) || !participantUniqueStrings(item.EvidenceRefs) || !participantUniqueStrings(item.Diagnostics) {
			return false
		}
	}
	return true
}
func (result participantActionResult) effectsValid() bool {
	ids := map[string]bool{}
	for _, item := range result.Effects {
		if item.ID == "" || item.Description == "" || ids[item.ID] {
			return false
		}
		ids[item.ID] = true
		if !participantUniqueStrings(item.TargetRefs) || !participantUniqueStrings(item.EvidenceRefs) || !participantUniqueStrings(item.Diagnostics) {
			return false
		}
		if item.Class != "no_effect" && item.Class != "unknown_effect" && len(item.TargetRefs)+len(item.EvidenceRefs) == 0 {
			return false
		}
	}
	return true
}
func (result participantActionResult) contractViolations(action participantAction, address string, violations *participantViolations) {
	if result.Action != address {
		violations.add(fmt.Sprintf("action_result action_contract_address %s does not match compiled action contract %s", pyrepr.Quote(result.Action), pyrepr.Quote(address)))
		return
	}
	result.preconditionViolations(action, address, violations)
	result.effectViolations(action, address, violations)
	result.evidenceViolations(action, violations)
	if result.Failure != nil && !slices.Contains(action.FailureClasses, *result.Failure) {
		violations.add(fmt.Sprintf("action_result failure_class %s is not declared by %s", pyrepr.Quote(*result.Failure), address))
	}
}

type participantDeclarationKey struct{ id, class string }

func (result participantActionResult) preconditionViolations(action participantAction, address string, violations *participantViolations) {
	if !violations.spend(len(action.preconditions) + len(result.Preconditions)) {
		return
	}
	declared := map[participantDeclarationKey]participantConditionDeclaration{}
	for _, item := range action.preconditions {
		declared[participantDeclarationKey{item.ID, item.Class}] = item
	}
	reported := map[participantDeclarationKey]bool{}
	for _, item := range result.Preconditions {
		key := participantDeclarationKey{item.ID, item.Class}
		reported[key] = true
		if !slices.Contains(action.PreconditionClasses, item.Class) {
			violations.add(fmt.Sprintf("action_result precondition %s uses undeclared precondition_class %s", pyrepr.Quote(item.ID), pyrepr.Quote(item.Class)))
		}
		definition, present := declared[key]
		if len(declared) > 0 && !present {
			violations.add(fmt.Sprintf("action_result precondition %s/%s is not declared by %s", pyrepr.Quote(item.ID), pyrepr.Quote(item.Class), address))
		}
		if present {
			participantPreconditionRefViolations(item, definition, violations)
		}
	}
	result.missingPreconditionViolations(declared, reported, address, violations)
}
func participantPreconditionRefViolations(item participantResultPrecondition, definition participantConditionDeclaration, violations *participantViolations) {
	for _, ref := range violations.difference(item.SupportRefs, definition.SupportRefs) {
		violations.add(fmt.Sprintf("action_result precondition %s reports undeclared support_ref %s", pyrepr.Quote(item.ID), pyrepr.Quote(ref)))
	}
	for _, ref := range violations.difference(item.EvidenceRefs, definition.EvidenceRefs) {
		violations.add(fmt.Sprintf("action_result precondition %s reports undeclared evidence_ref %s", pyrepr.Quote(item.ID), pyrepr.Quote(ref)))
	}
}
func (result participantActionResult) missingPreconditionViolations(declared map[participantDeclarationKey]participantConditionDeclaration, reported map[participantDeclarationKey]bool, address string, violations *participantViolations) {
	missing := []participantDeclarationKey{}
	for key := range declared {
		if !reported[key] {
			missing = append(missing, key)
		}
	}
	slices.SortFunc(missing, func(a, b participantDeclarationKey) int {
		if a.id != b.id {
			return strings.Compare(a.id, b.id)
		}
		return strings.Compare(a.class, b.class)
	})
	for _, key := range missing {
		violations.add(fmt.Sprintf("action_result is missing declared precondition %s/%s for %s", pyrepr.Quote(key.id), pyrepr.Quote(key.class), address))
	}
}
func (result participantActionResult) effectViolations(action participantAction, address string, violations *participantViolations) {
	if !violations.spend(len(action.effects) + len(result.Effects)) {
		return
	}
	declared := map[participantDeclarationKey]participantEffectDeclaration{}
	for _, item := range action.effects {
		declared[participantDeclarationKey{item.ID, item.Class}] = item
	}
	for _, item := range result.Effects {
		if !slices.Contains(action.EffectClasses, item.Class) {
			violations.add(fmt.Sprintf("action_result effect %s uses undeclared effect_class %s", pyrepr.Quote(item.ID), pyrepr.Quote(item.Class)))
		}
		definition, present := declared[participantDeclarationKey{item.ID, item.Class}]
		if len(declared) > 0 && !present {
			violations.add(fmt.Sprintf("action_result effect %s/%s is not declared by %s", pyrepr.Quote(item.ID), pyrepr.Quote(item.Class), address))
		}
		if present {
			participantEffectRefViolations(item, definition, violations)
		}
	}
}
func participantEffectRefViolations(item participantResultEffect, definition participantEffectDeclaration, violations *participantViolations) {
	for _, ref := range violations.difference(item.TargetRefs, definition.TargetRefs) {
		violations.add(fmt.Sprintf("action_result effect %s reports undeclared target_ref %s", pyrepr.Quote(item.ID), pyrepr.Quote(ref)))
	}
	for _, ref := range violations.difference(item.EvidenceRefs, definition.EvidenceRefs) {
		violations.add(fmt.Sprintf("action_result effect %s reports undeclared evidence_ref %s", pyrepr.Quote(item.ID), pyrepr.Quote(ref)))
	}
}
func (result participantActionResult) evidenceViolations(action participantAction, violations *participantViolations) {
	if len(action.preconditions)+len(action.effects) == 0 {
		return
	}
	declared := []string{}
	reported := []string{}
	for _, item := range action.preconditions {
		declared = append(declared, item.EvidenceRefs...)
	}
	for _, item := range action.effects {
		declared = append(declared, item.EvidenceRefs...)
	}
	for _, item := range result.Preconditions {
		reported = append(reported, item.EvidenceRefs...)
	}
	for _, item := range result.Effects {
		reported = append(reported, item.EvidenceRefs...)
	}
	for _, ref := range violations.difference(result.EvidenceRefs, declared) {
		violations.add("action_result reports undeclared evidence_ref " + pyrepr.Quote(ref))
	}
	for _, ref := range violations.difference(result.EvidenceRefs, reported) {
		if slices.Contains(declared, ref) {
			violations.add(fmt.Sprintf("action_result evidence_ref %s is not grounded in reported precondition or effect evidence_refs", pyrepr.Quote(ref)))
		}
	}
}

// ParticipantActionResultViolations compares a typed local result with its compiled contract.
func ParticipantActionResultViolations(model RuntimeModel, actionContractAddress string, result admission.Fragment) ([]diagnostic.Diagnostic, error) {
	owned, err := nativeRuntimeModel(model)
	if err != nil {
		return nil, err
	}
	action, ok := owned.participants.actions[actionContractAddress]
	if !ok {
		return nil, participantContractInput()
	}
	var record participantActionResult
	if err := participantFragmentDecode(result, admission.ParticipantActionResult, &record); err != nil {
		return nil, err
	}
	if !record.locallyValid() {
		return nil, participantContractInput()
	}
	violations := newParticipantViolations()
	record.contractViolations(action, actionContractAddress, violations)
	if violations.err != nil {
		return nil, violations.err
	}
	return participantFindings("participant.action-result-contract-violation", actionContractAddress, violations.messages), nil
}
