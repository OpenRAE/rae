package profile

import "slices"

// ValidationStrength is one ranked strength of the validation catalog.
type ValidationStrength struct {
	ID   string
	Rank int
}

// ValidationProfile is one exact validation-profile identity.
type ValidationProfile struct {
	ID, Version, Title, MinimumStrength                              string
	SubjectKinds, RequiredGates, OptionalGates, LimitationCategories []string
	EvidenceExpectations, DiagnosticExpectations                     []string
	ExtensionTermsAllowed                                            bool
}

// ValidationCatalog is the packaged validation-profile catalog.
type ValidationCatalog struct {
	Version                                       string
	Strengths                                     []ValidationStrength
	SubjectKinds, GateKinds, LimitationCategories []string
	Profiles                                      []ValidationProfile
}

type validationWire struct {
	CatalogVersion string `json:"catalog_version"`
	Strengths      []struct {
		ID   string `json:"strength_id"`
		Rank int    `json:"rank"`
	} `json:"strengths"`
	SubjectKinds []struct {
		ID string `json:"subject_kind"`
	} `json:"subject_kinds"`
	GateKinds []struct {
		ID string `json:"gate_kind"`
	} `json:"gate_kinds"`
	LimitationCategories []struct {
		ID string `json:"limitation_category"`
	} `json:"limitation_categories"`
	Profiles []struct {
		ID                     string   `json:"profile_id"`
		Version                string   `json:"profile_version"`
		Title                  string   `json:"title"`
		SubjectKinds           []string `json:"intended_subject_kinds"`
		MinimumStrength        string   `json:"minimum_strength"`
		RequiredGates          []string `json:"required_gate_kinds"`
		OptionalGates          []string `json:"optional_gate_kinds"`
		EvidenceExpectations   []string `json:"evidence_expectations"`
		DiagnosticExpectations []string `json:"diagnostic_expectations"`
		LimitationCategories   []string `json:"limitation_categories"`
		ExtensionTermsAllowed  bool     `json:"extension_terms_allowed"`
	} `json:"profiles"`
}

func (p *Profiles) decodeValidation(documents map[string][]byte) error {
	var wire validationWire
	if err := decode(documents[pathValidation], &wire); err != nil {
		return err
	}
	catalog := ValidationCatalog{Version: wire.CatalogVersion}
	for _, row := range wire.Strengths {
		catalog.Strengths = append(catalog.Strengths, ValidationStrength{ID: row.ID, Rank: row.Rank})
	}
	for _, row := range wire.SubjectKinds {
		catalog.SubjectKinds = append(catalog.SubjectKinds, row.ID)
	}
	for _, row := range wire.GateKinds {
		catalog.GateKinds = append(catalog.GateKinds, row.ID)
	}
	for _, row := range wire.LimitationCategories {
		catalog.LimitationCategories = append(catalog.LimitationCategories, row.ID)
	}
	for _, row := range wire.Profiles {
		catalog.Profiles = append(catalog.Profiles, ValidationProfile{ID: row.ID, Version: row.Version, Title: row.Title, MinimumStrength: row.MinimumStrength, SubjectKinds: row.SubjectKinds, RequiredGates: row.RequiredGates, OptionalGates: row.OptionalGates, LimitationCategories: row.LimitationCategories, EvidenceExpectations: row.EvidenceExpectations, DiagnosticExpectations: row.DiagnosticExpectations, ExtensionTermsAllowed: row.ExtensionTermsAllowed})
	}
	p.validation = catalog
	return nil
}

// ValidationCatalog returns the packaged catalog.
func (p *Profiles) ValidationCatalog() ValidationCatalog {
	catalog := p.validation
	catalog.Strengths = slices.Clone(catalog.Strengths)
	catalog.SubjectKinds, catalog.GateKinds, catalog.LimitationCategories = slices.Clone(catalog.SubjectKinds), slices.Clone(catalog.GateKinds), slices.Clone(catalog.LimitationCategories)
	catalog.Profiles = slices.Clone(catalog.Profiles)
	for i := range catalog.Profiles {
		catalog.Profiles[i] = catalog.Profiles[i].copy()
	}
	return catalog
}

// SelectValidationProfile returns the exact profile identity that declares
// the subject kind. An unknown identity or an undeclared subject kind is an
// InvalidInput fault.
func (p *Profiles) SelectValidationProfile(id, version, subjectKind string) (ValidationProfile, error) {
	for _, profile := range p.validation.Profiles {
		if profile.ID != id || profile.Version != version {
			continue
		}
		if !slices.Contains(profile.SubjectKinds, subjectKind) {
			return ValidationProfile{}, invalid("validation-profile-subject-undeclared")
		}
		return profile.copy(), nil
	}
	return ValidationProfile{}, invalid("validation-profile-unknown")
}

func (v ValidationProfile) copy() ValidationProfile {
	for _, list := range []*[]string{&v.SubjectKinds, &v.RequiredGates, &v.OptionalGates, &v.LimitationCategories, &v.EvidenceExpectations, &v.DiagnosticExpectations} {
		*list = slices.Clone(*list)
	}
	return v
}
