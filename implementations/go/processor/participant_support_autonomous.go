package processor

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type autonomousCapabilities struct {
	MaxParticipants            *json.Number               `json:"max_autonomous_participants"`
	MaxActionAttempts          *json.Number               `json:"max_autonomous_action_attempts"`
	MaxInFlight                *json.Number               `json:"max_autonomous_in_flight"`
	MaxOccurrences             *json.Number               `json:"max_autonomous_occurrences"`
	MaxRetries                 *json.Number               `json:"max_autonomous_retries_per_occurrence"`
	MaxBurstSize               *json.Number               `json:"max_autonomous_burst_size"`
	MaxConcurrentActions       *json.Number               `json:"max_concurrent_actions"`
	SupportsBoundedConcurrency bool                       `json:"supports_bounded_concurrency"`
	SelectionStrategies        []string                   `json:"supported_autonomous_selection_strategies"`
	ActionContracts            []string                   `json:"supported_autonomous_action_contracts"`
	ObservationBoundaries      []string                   `json:"supported_autonomous_observation_boundaries"`
	Targets                    []string                   `json:"supported_autonomous_target_addresses"`
	Profiles                   []string                   `json:"supported_autonomous_policy_profiles"`
	ActivityFeatures           []string                   `json:"supported_autonomous_activity_features"`
	RandomStreamProfiles       []string                   `json:"supported_autonomous_random_stream_profiles"`
	ExecutionBindings          []autonomousExecutionOffer `json:"execution_bindings"`
	ResourceBudgets            json.RawMessage            `json:"resource_budgets"`
}

type autonomousExecutionOffer struct {
	ActionContractAddress   string      `json:"action_contract_address"`
	ImplementationRef       string      `json:"participant_implementation_ref"`
	Targets                 []string    `json:"target_addresses"`
	MaxActionAttempts       json.Number `json:"max_action_attempts"`
	MaxInFlight             json.Number `json:"max_in_flight"`
	TemporalContractDigests []string    `json:"temporal_contract_digests"`
}

func exactInteger(value json.Number) *big.Int {
	if value == "" {
		return new(big.Int)
	}
	// Native admission already bounds the coefficient and exponent. Schema
	// integers may retain decimal or exponent spellings in transport values.
	result, ok := new(big.Rat).SetString(string(value))
	if !ok || !result.IsInt() {
		panic("processor: invalid owned integer")
	}
	return result.Num()
}
func numberMaximum(values ...json.Number) json.Number {
	result := json.Number("0")
	for _, value := range values {
		if exactInteger(value).Cmp(exactInteger(result)) > 0 {
			result = value
		}
	}
	return result
}
func sameStringSet(a, b []string) bool {
	left, right := slices.Clone(a), slices.Clone(b)
	slices.Sort(left)
	slices.Sort(right)
	return slices.Equal(slices.Compact(left), slices.Compact(right))
}
func missingStrings(required, supported []string) []string {
	missing := []string{}
	for _, item := range required {
		if !slices.Contains(supported, item) {
			missing = append(missing, item)
		}
	}
	slices.Sort(missing)
	return slices.Compact(missing)
}

type autonomousDemandSummary struct {
	participants, strategies, actions, observations, targets, profiles, activities []string
	attempts, inflight, occurrences, retries, burst                                json.Number
	activity                                                                       bool
}

func autonomousCapabilityGaps(model *runtimeModel, manifest binding.BackendManifestV2, capability *participantRuntimeCapability, policies []*participantAutonomous) ([]string, error) {
	if capability == nil || !capability.SupportsAutonomous {
		return []string{"backend does not declare autonomous participant execution"}, nil
	}
	summary := autonomousDemandSummary{attempts: "0", inflight: "0", occurrences: "0", retries: "0", burst: "0"}
	for _, policy := range policies {
		summary.include(policy)
	}
	caps := capability.autonomousCapabilities
	gaps := summary.limitGaps(caps)
	gaps = append(gaps, summary.valueGaps(caps)...)
	gaps = append(gaps, autonomousBindingGaps(caps, policies)...)
	budgets, err := participantResourceSupportGaps(manifest, caps.ResourceBudgets, policies)
	if err != nil {
		return nil, err
	}
	gaps = append(gaps, budgets...)
	reset, err := autonomousResetGaps(model, manifest, policies)
	if err != nil {
		return nil, err
	}
	gaps = append(gaps, reset...)
	return append(gaps, autonomousTemporalGaps(model, policies)...), nil
}

func (s *autonomousDemandSummary) include(policy *participantAutonomous) {
	s.participants = append(s.participants, policy.ParticipantAddresses...)
	s.attempts = numberMaximum(s.attempts, policy.MaxActionAttempts)
	s.inflight = numberMaximum(s.inflight, policy.MaxInFlight)
	s.burst = numberMaximum(s.burst, policy.MaxBurstSize)
	count := policy.MaxOccurrences
	if exactInteger(count).Sign() == 0 {
		count = policy.MaxActionAttempts
	}
	s.occurrences = numberMaximum(s.occurrences, count)
	for _, count := range policy.ActionCandidateMaxRetries {
		s.retries = numberMaximum(s.retries, count)
	}
	s.strategies = append(s.strategies, policy.SelectionStrategy)
	s.actions = append(s.actions, policy.ActionContractAddresses...)
	s.observations = append(s.observations, policy.ObservationBoundaryAddress)
	s.targets = append(s.targets, policy.TargetAddresses...)
	s.profiles = append(s.profiles, policy.Profile)
	if policy.Profile == "participant-autonomous-execution/v2" || policy.Profile == termParticipantAutonomousExecutionV3 {
		s.activity = true
		s.activities = append(s.activities, autonomousActivityFeatures(policy)...)
	}
}

func autonomousActivityFeatures(policy *participantAutonomous) []string {
	features := []string{"work-windows", "weighted-selection", "occurrence-provenance"}
	if exactInteger(policy.TimingMinimumTicks).Cmp(exactInteger(policy.TimingMaximumTicks)) != 0 {
		features = append(features, "timing-variation")
	}
	if slices.ContainsFunc(policy.ActionCandidateDependencies, func(values []string) bool { return len(values) > 0 }) {
		features = append(features, "dependencies")
	}
	if slices.ContainsFunc(policy.ActionCandidateMaxRetries, positiveNumber) {
		features = append(features, "bounded-retries")
	}
	if slices.ContainsFunc(policy.ActionCandidateCooldownTicks, positiveNumber) {
		features = append(features, "cooldowns")
	}
	if exactInteger(policy.MaxBurstSize).Cmp(big.NewInt(1)) > 0 {
		features = append(features, "limited-bursts")
	}
	return features
}

func positiveNumber(value json.Number) bool { return exactInteger(value).Sign() > 0 }

func (s *autonomousDemandSummary) limitGaps(caps autonomousCapabilities) []string {
	slices.Sort(s.participants)
	s.participants = slices.Compact(s.participants)
	gaps := []string{}
	for _, item := range []struct {
		label    string
		required *big.Int
		maximum  *json.Number
	}{
		{"participants", big.NewInt(int64(len(s.participants))), caps.MaxParticipants},
		{"action attempts", exactInteger(s.attempts), caps.MaxActionAttempts},
		{"in-flight actions", exactInteger(s.inflight), caps.MaxInFlight},
		{"occurrences", exactInteger(s.occurrences), caps.MaxOccurrences},
		{"retries per occurrence", exactInteger(s.retries), caps.MaxRetries},
		{"burst size", exactInteger(s.burst), caps.MaxBurstSize},
	} {
		if item.maximum == nil || item.required.Cmp(exactInteger(*item.maximum)) > 0 {
			maximum := "None"
			if item.maximum != nil {
				maximum = exactInteger(*item.maximum).String()
			}
			gaps = append(gaps, "autonomous "+item.label+" require "+item.required.String()+", backend limit is "+maximum)
		}
	}
	return append(gaps, autonomousConcurrencyGaps(s.inflight, caps)...)
}

func autonomousConcurrencyGaps(inflight json.Number, caps autonomousCapabilities) []string {
	gaps := []string{}
	if exactInteger(inflight).Cmp(big.NewInt(1)) > 0 && !caps.SupportsBoundedConcurrency {
		gaps = append(gaps, "autonomous in-flight actions require bounded concurrency support")
	}
	if caps.MaxConcurrentActions == nil || exactInteger(inflight).Cmp(exactInteger(*caps.MaxConcurrentActions)) > 0 {
		maximum := "None"
		if caps.MaxConcurrentActions != nil {
			maximum = exactInteger(*caps.MaxConcurrentActions).String()
		}
		gaps = append(gaps, "autonomous in-flight actions require "+string(inflight)+", backend concurrent-action limit is "+maximum)
	}
	return gaps
}

func (s *autonomousDemandSummary) valueGaps(caps autonomousCapabilities) []string {
	gaps := []string{}
	for _, item := range []struct {
		label               string
		required, supported []string
	}{
		{"selection strategies", s.strategies, caps.SelectionStrategies},
		{"action contracts", s.actions, caps.ActionContracts},
		{"observation boundaries", s.observations, caps.ObservationBoundaries},
		{"target addresses", s.targets, caps.Targets},
		{"policy profiles", s.profiles, caps.Profiles},
	} {
		if missing := missingStrings(item.required, item.supported); len(missing) > 0 {
			gaps = append(gaps, "unsupported autonomous "+item.label+": "+strings.Join(missing, ", "))
		}
	}
	if s.activity {
		if missing := missingStrings(s.activities, caps.ActivityFeatures); len(missing) > 0 {
			gaps = append(gaps, "unsupported autonomous activity features: "+strings.Join(missing, ", "))
		}
		if !slices.Contains(caps.RandomStreamProfiles, "blake3-xof-participant-v1") {
			gaps = append(gaps, "unsupported autonomous random-stream profiles: blake3-xof-participant-v1")
		}
	}
	return gaps
}

func autonomousBindingGaps(caps autonomousCapabilities, policies []*participantAutonomous) []string {
	bindings := map[[2]string][]autonomousExecutionOffer{}
	for _, offer := range caps.ExecutionBindings {
		key := [2]string{offer.ActionContractAddress, offer.ImplementationRef}
		bindings[key] = append(bindings[key], offer)
	}
	gaps := []string{}
	for _, policy := range policies {
		for _, required := range policy.ExecutionBindings {
			key := [2]string{required.ActionContractAddress, required.ParticipantImplementationRef}
			if !autonomousBindingSupported(bindings[key], required, requiredTemporalDigests(policy, required.ActionContractAddress)) {
				gaps = append(gaps, "unsupported autonomous execution binding or temporal guarantee for "+required.ActionContractAddress+" targets: "+strings.Join(required.TargetAddresses, ", "))
			}
		}
	}
	return gaps
}

func requiredTemporalDigests(policy *participantAutonomous, address string) []string {
	digests := []string{}
	for _, binding := range policy.TemporalBindings {
		if binding.ActionContractAddress == address {
			digests = append(digests, binding.ContractDigest)
		}
	}
	return digests
}

func autonomousBindingSupported(offers []autonomousExecutionOffer, required participantExecutionBinding, digests []string) bool {
	for _, offer := range offers {
		if sameStringSet(offer.Targets, required.TargetAddresses) && exactInteger(offer.MaxActionAttempts).Cmp(exactInteger(required.MaxActionAttempts)) >= 0 && exactInteger(offer.MaxInFlight).Cmp(exactInteger(required.MaxInFlight)) >= 0 && len(missingStrings(digests, offer.TemporalContractDigests)) == 0 {
			return true
		}
	}
	return false
}

func autonomousResetRequired(model *runtimeModel, policies []*participantAutonomous) bool {
	progression := map[string]TimePolicy{}
	for _, policy := range model.view.TimeModel.ProgressionPolicies {
		progression[policy.Address] = policy
	}
	for _, policy := range policies {
		if selected, exists := progression[policy.ProgressionPolicyAddress]; exists && (selected.ResetBehavior != "unsupported" || selected.ReplayBehavior != "unsupported") {
			return true
		}
	}
	return false
}

func autonomousResetGaps(model *runtimeModel, manifest binding.BackendManifestV2, policies []*participantAutonomous) ([]string, error) {
	if !autonomousResetRequired(model, policies) {
		return []string{}, nil
	}
	var caps struct {
		Coordinated bool `json:"supports_coordinated_participant_reset"`
	}
	raw := fieldValue(fieldValue(manifest.Capabilities).Time)
	if len(raw) > 0 && json.Unmarshal(raw, &caps) != nil {
		return nil, invalidCompiled()
	}
	if !caps.Coordinated {
		return []string{"autonomous clock reset requires coordinated participant reset support"}, nil
	}
	return []string{}, nil
}

func autonomousTemporalGaps(model *runtimeModel, policies []*participantAutonomous) []string {
	constraints := map[string]TemporalConstraint{}
	for _, constraint := range model.view.TimeModel.Constraints {
		constraints[constraint.Address] = constraint
	}
	gaps := []string{}
	for _, policy := range policies {
		if policy.Profile == "participant-autonomous-execution/v1" {
			gaps = append(gaps, autonomousPolicyTemporalGaps(policy, constraints)...)
		}
	}
	return gaps
}

func autonomousPolicyTemporalGaps(policy *participantAutonomous, constraints map[string]TemporalConstraint) []string {
	bound := map[string]bool{}
	for _, binding := range policy.TemporalBindings {
		bound[binding.ConstraintAddress] = true
	}
	gaps := []string{}
	for _, address := range policy.TemporalConstraintAddresses {
		if constraint, exists := constraints[address]; exists && constraint.Kind != "cadence" && !bound[address] {
			gaps = append(gaps, "autonomous "+constraint.Kind+" constraint "+address+" requires an explicit action temporal binding")
		}
	}
	return gaps
}
