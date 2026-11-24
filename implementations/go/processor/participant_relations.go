package processor

import (
	"bytes"
	"encoding/json"
	"slices"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

const participantRelationWork = 100000

type participantWork struct{ remaining int }

func (work *participantWork) spend(count int) bool {
	if count < 0 || count > work.remaining {
		return false
	}
	work.remaining -= count
	return true
}
func participantContractInput() error {
	return fault.New(fault.InvalidInput, "processor-participant-contract", nil)
}
func participantArgumentInput() error {
	return fault.New(fault.InvalidInput, "processor-action-arguments", nil)
}

func participantFragmentBytes(input admission.Fragment, profile admission.FragmentProfile) ([]byte, error) {
	if err := admission.CheckFragment(input, profile); err != nil {
		return nil, err
	}
	limits := value.Runtime()
	limits.MaxOperations = participantRelationWork
	raw, err := value.Encode(input.Document(), limits)
	if err != nil || len(raw) > 8<<20 {
		return nil, participantContractInput()
	}
	return raw, nil
}
func participantDecode(raw []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if decoder.Decode(target) != nil {
		return participantContractInput()
	}
	return nil
}
func participantFragmentDecode(input admission.Fragment, profile admission.FragmentProfile, target any) error {
	raw, err := participantFragmentBytes(input, profile)
	if err != nil {
		return err
	}
	return participantDecode(raw, target)
}
func participantFinding(code, address, pointer, message string) diagnostic.Diagnostic {
	return diagnostic.Diagnostic{Code: code, Domain: termParticipant, Address: address, Pointer: pointer, Message: message, Severity: termError}
}
func participantFindings(code, address string, messages []string) []diagnostic.Diagnostic {
	findings := make([]diagnostic.Diagnostic, len(messages))
	for index, message := range messages {
		findings[index] = participantFinding(code, address, "", message)
	}
	return findings
}
func participantStringDifference(left, right []string) []string {
	values := map[string]bool{}
	for _, item := range right {
		values[item] = true
	}
	result := []string{}
	for _, item := range sortedTerms(left) {
		if !values[item] {
			result = append(result, item)
		}
	}
	return result
}
func participantStringsValid(values []string) bool {
	return !slices.Contains(values, "")
}
func participantUniqueStrings(values []string) bool {
	copied := slices.Clone(values)
	slices.Sort(copied)
	return participantStringsValid(values) && len(slices.Compact(copied)) == len(values)
}

func participantRelationLimits() ingress.Limits {
	return ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
}

// ParticipantFailureClass uses only the exact declared backend diagnostic code.
func ParticipantFailureClass(model RuntimeModel, actionContractAddress, backendErrorCode string) (string, error) {
	owned, err := nativeRuntimeModel(model)
	if err != nil {
		return "", err
	}
	action, ok := owned.participants.actions[actionContractAddress]
	if !ok || len(backendErrorCode) > 1<<20 || !utf8.ValidString(backendErrorCode) {
		return "", participantContractInput()
	}
	for _, mapping := range action.BackendFailureMappings {
		if mapping.BackendErrorCode == backendErrorCode {
			return mapping.FailureClass, nil
		}
	}
	if backendErrorCode == "" {
		return termUnknown, nil
	}
	return "backend_error", nil
}
