package sdl

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// ComparisonSubject retains the native type and supplied fields of a child.
type ComparisonSubject struct {
	Family, Name, ModelType string
	PresentFields           []string
	Semantic                admission.Fragment
}

// ComparisonProjection contains independent native owner facts for pure
// comparison. Version is the artifact version, not the projection revision.
type ComparisonProjection struct {
	Name, Version, CanonicalDigest string
	Structural, Semantic           admission.Fragment
	Subjects                       []ComparisonSubject
	Imports                        []admission.Fragment
}
type comparisonWireSubject struct {
	Family        string          `json:"Family"`
	Name          string          `json:"Name"`
	ModelType     string          `json:"ModelType"`
	PresentFields []string        `json:"PresentFields"`
	Semantic      json.RawMessage `json:"Semantic"`
}
type comparisonWire struct {
	Name            string                  `json:"Name"`
	Version         string                  `json:"Version"`
	CanonicalDigest string                  `json:"CanonicalDigest"`
	Structural      json.RawMessage         `json:"Structural"`
	Semantic        json.RawMessage         `json:"Semantic"`
	Subjects        []comparisonWireSubject `json:"Subjects"`
	Imports         []json.RawMessage       `json:"Imports"`
}

// ProjectComparison projects an exact native authored constructor. It makes
// no claim of contextual validity, compatibility or execution authority.
func ProjectComparison(source Scenario, version string) (ComparisonProjection, error) {
	owned, ok := source.(*scenario)
	if !ok || owned == nil || owned.document == nil || owned.parser == nil {
		return ComparisonProjection{}, invalidScenario()
	}
	raw, err := owned.parser.ComparisonProjection(owned.document, version)
	if err != nil {
		return ComparisonProjection{}, err
	}
	var wire comparisonWire
	if err = json.Unmarshal(raw, &wire); err != nil {
		return ComparisonProjection{}, err
	}
	return admitComparisonProjection(wire)
}
func admitComparisonProjection(wire comparisonWire) (ComparisonProjection, error) {
	result := ComparisonProjection{Name: wire.Name, Version: wire.Version, CanonicalDigest: wire.CanonicalDigest, Subjects: []ComparisonSubject{}, Imports: []admission.Fragment{}}
	var err error
	result.Structural, err = comparisonFragment(wire.Structural)
	if err != nil {
		return ComparisonProjection{}, err
	}
	result.Semantic, err = comparisonFragment(wire.Semantic)
	if err != nil {
		return ComparisonProjection{}, err
	}
	for _, subject := range wire.Subjects {
		semantic, err := comparisonFragment(subject.Semantic)
		if err != nil {
			return ComparisonProjection{}, err
		}
		result.Subjects = append(result.Subjects, ComparisonSubject{Family: subject.Family, Name: subject.Name, ModelType: subject.ModelType, PresentFields: subject.PresentFields, Semantic: semantic})
	}
	for _, input := range wire.Imports {
		fragment, err := comparisonFragment(input)
		if err != nil {
			return ComparisonProjection{}, err
		}
		result.Imports = append(result.Imports, fragment)
	}
	return result, nil
}

//nolint:ireturn // The projection boundary admits sealed native JSON fragments.
func comparisonFragment(raw []byte) (admission.Fragment, error) {
	document, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return nil, err
	}
	owner, err := fragmentOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(owner, admission.RealizationValue, document, ingress.Limits{MaxBytes: 16 << 20, MaxDepth: 64})
}
