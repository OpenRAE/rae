package sdl

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/concept"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// ConceptSubjects returns the native semantic subjects for concept admission.
func ConceptSubjects(scenario Scenario) ([]concept.Subject, error) {
	s, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	return s.document.ConceptSubjects()
}

// Requirement binds an artifact contract to its structural source trail.
type Requirement struct {
	Trail    []string
	Document binding.ArtifactRequirementV1
}

// ArtifactRequirements returns artifact requirements selected by the native SDL schema.
func ArtifactRequirements(scenario Scenario) ([]Requirement, error) {
	input, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	sources, err := input.document.ArtifactSources()
	if err != nil {
		return nil, err
	}
	result := make([]Requirement, 0, len(sources))
	// Source maps are keyed by structural pointer; report order is stable.
	for _, pointer := range slices.Sorted(maps.Keys(sources)) {
		raw, err := json.Marshal(struct {
			Version string          `json:"schema_version"`
			Source  json.RawMessage `json:"source"`
		}{"artifact-requirement/v1", sources[pointer]})
		if err != nil {
			return nil, err
		}
		var document binding.ArtifactRequirementV1
		if json.Unmarshal(raw, &document) != nil {
			return nil, invalidScenario()
		}
		result = append(result, Requirement{Trail: append(jsonpointer.Tokens(pointer), "artifact_requirement"), Document: document})
	}
	return result, nil
}

type designationRecord struct {
	Namespace []string `json:"namespace"`
	Pointer   string   `json:"field_pointer"`
	Posture   string   `json:"posture"`
}

// ResolveRealizationDesignation resolves lexical authority for one authored field.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ResolveRealizationDesignation(scenario Scenario, fieldPointer string) (admission.Fragment, error) {
	owner := []string{}
	tokens := jsonpointer.Tokens(fieldPointer)
	if len(tokens) >= 2 {
		name := tokens[1]
		if before, _, ok := strings.CutLast(name, "."); ok {
			owner = strings.Split(before, ".")
		}
	}
	return ResolveRealizationDesignationForNamespace(scenario, fieldPointer, owner)
}

// ResolveRealizationDesignationForNamespace queries the same lexical owner
// for an enclosing collection without substituting a child declaration scope.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func ResolveRealizationDesignationForNamespace(scenario Scenario, fieldPointer string, namespace []string) (admission.Fragment, error) {
	s, err := nativeScenario(scenario)
	if err != nil || !s.document.Validated() || !designationQueryValid(fieldPointer, namespace) {
		return nil, invalidScenario()
	}
	s.designationOnce.Do(s.loadDesignations)
	if s.designationErr != nil {
		return nil, s.designationErr
	}
	governing, delegated := selectDesignations(s.designations, namespace, fieldPointer)
	return designationResult(governing, delegated)
}

func designationQueryValid(pointer string, namespace []string) bool {
	if len(pointer) > 4096 || pointer != jsonpointer.FromTokens(jsonpointer.Tokens(pointer)) || len(namespace) > 32 {
		return false
	}
	for _, part := range namespace {
		if len(part) == 0 || len(part) > 64 {
			return false
		}
	}
	return true
}

func selectDesignations(records []designationRecord, owner []string, fieldPointer string) (*designationRecord, *designationRecord) {
	var governing, delegated *designationRecord
	for index := range records {
		record := &records[index]
		if len(record.Namespace) > len(owner) || !slices.Equal(record.Namespace, owner[:len(record.Namespace)]) || !pointerContains(record.Pointer, fieldPointer) {
			continue
		}
		if record.Posture == "unspecified" {
			if delegated == nil || moreSpecific(*record, *delegated) {
				delegated = record
			}
		} else if governing == nil || moreSpecific(*record, *governing) {
			governing = record
		}
	}
	return governing, delegated
}

//nolint:ireturn // The shared admission owner issues the sealed designation handle.
func designationResult(governing, delegated *designationRecord) (admission.Fragment, error) {
	closure, origin := "closed-world", "legacy-default"
	var scope any
	wasDelegated := false
	if governing != nil {
		origin = "scope"
		if governing.Posture == termOpen {
			closure = "open-world"
		}
	} else if delegated != nil {
		governing, wasDelegated, origin = delegated, true, "apparatus-default"
	}
	if governing != nil {
		pointer := governing.Pointer
		if pointer == "" {
			pointer = "/"
		}
		scope = strings.Join(governing.Namespace, ".") + "#" + pointer
	}
	return admitDesignation(map[string]any{"closure": closure, "governing_scope": scope, "delegated": wasDelegated, "source": origin})
}

func (s *scenario) loadDesignations() {
	raw, err := s.document.RealizationDesignations()
	if err != nil || json.Unmarshal(raw, &s.designations) != nil {
		s.designationErr = invalidScenario()
	}
}

func pointerContains(scope, pointer string) bool {
	a, b := jsonpointer.Tokens(scope), jsonpointer.Tokens(pointer)
	return len(a) <= len(b) && slices.Equal(a, b[:len(a)])
}
func moreSpecific(a, b designationRecord) bool {
	if n, m := len(jsonpointer.Tokens(a.Pointer)), len(jsonpointer.Tokens(b.Pointer)); n != m {
		return n > m
	}
	if len(a.Namespace) != len(b.Namespace) {
		return len(a.Namespace) > len(b.Namespace)
	}
	if n, m := strings.Join(a.Namespace, "."), strings.Join(b.Namespace, "."); n != m {
		return n > m
	}
	return a.Pointer > b.Pointer
}

var fragmentOwner = sync.OnceValues(admission.New) //nolint:gochecknoglobals // Immutable packaged validation owner.

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func admitDesignation(document map[string]any) (admission.Fragment, error) {
	validator, err := fragmentOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(validator, admission.RealizationDesignation, document, ingress.Limits{MaxBytes: 1048576, MaxDepth: 32})
}

// ValidateExperimentSelectionAgainstFamily checks selection membership through the native family owner.
func ValidateExperimentSelectionAgainstFamily(spec binding.ExperimentAuthoringInputV1, family Scenario) (binding.ExperimentAuthoringInputV1, error) {
	s, err := nativeScenario(family)
	if err != nil {
		return binding.ExperimentAuthoringInputV1{}, err
	}
	return s.parser.ValidateExperimentSelectionAgainstFamily(spec, s.document)
}
