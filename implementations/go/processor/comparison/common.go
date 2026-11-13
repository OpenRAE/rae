package comparison

import (
	"bytes"
	"encoding/json"
	"slices"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

const (
	scenarioIdentityPrefix = "scenario:"
	kindScenario           = "scenario"
	kindModule             = "module"
	kindTask               = "task"
	kindRun                = "run"
	kindCapture            = "evidence-specification"
	kindStudy              = "study"
	kindExternal           = "external-concept-bindings"
	relationSame           = "same"
	relationChanged        = "changed"
	relationUnchanged      = "unchanged"
	relationAdded          = "added"
	relationRemoved        = "removed"
	relationIncomparable   = "incomparable"
	relationNotApplicable  = "not-applicable"
	reasonRepresentation   = "representation-evidence-missing"
	reasonSubjects         = "subject-bound-exhausted"
	reasonEdges            = "dependency-edge-bound-exhausted"
	reasonPaths            = "impact-path-bound-exhausted"
)

func invalid() error              { return fault.New(fault.InvalidInput, "processor-comparison-input", nil) }
func inputLimits() ingress.Limits { return ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64} }

type nativeOwners struct {
	admitted *admission.Validator
	low      *validation.Validator
}

var owners = sync.OnceValues(func() (nativeOwners, error) { //nolint:gochecknoglobals // Immutable stock validators are initialized once.
	admitted, err := admission.New()
	if err != nil {
		return nativeOwners{}, err
	}
	low, err := validation.New(nil)
	return nativeOwners{admitted, low}, err
})

func decode(raw []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if decoder.Decode(target) != nil {
		return invalid()
	}
	return nil
}
func hash(input any) (string, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return "", invalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", invalid()
	}
	return digest.SHA256(canonical), nil
}
func sortedUnique(input []string) []string {
	result := append([]string{}, input...)
	slices.Sort(result)
	return slices.Compact(result)
}
func fragmentBytes(input admission.Fragment, profile admission.FragmentProfile) ([]byte, error) {
	if admission.CheckFragment(input, profile) != nil {
		return nil, invalid()
	}
	raw, err := value.Encode(input.Document(), value.Runtime())
	if err != nil || len(raw) > 8<<20 {
		return nil, invalid()
	}
	return raw, nil
}

//nolint:ireturn // Only the existing exact fragment owner constructs output handles.
func admitFragment(profile admission.FragmentProfile, input any) (admission.Fragment, error) {
	owner, err := owners()
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, invalid()
	}
	document, err := ingress.Parse(raw, inputLimits(), ingress.Object)
	if err != nil {
		return nil, invalid()
	}
	return admission.AdmitFragment(owner.admitted, profile, document, inputLimits())
}
func native(input Artifact) (*artifact, error) {
	owned, ok := input.(*artifact)
	if !ok || owned == nil {
		return nil, invalid()
	}
	return owned, nil
}
func lessCoordinate(a, b coordinate) int {
	for _, pair := range [][2]string{{a.Kind, b.Kind}, {a.Identity, b.Identity}, {a.Digest, b.Digest}} {
		if pair[0] < pair[1] {
			return -1
		}
		if pair[0] > pair[1] {
			return 1
		}
	}
	return 0
}
func equalCoordinates(a, b coordinate) bool {
	if (a.Exact == nil) != (b.Exact == nil) {
		return false
	}
	if a.Exact != nil && *a.Exact != *b.Exact {
		return false
	}
	a.Exact, b.Exact = nil, nil
	return a == b
}
