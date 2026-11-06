package profile

import (
	"maps"
	"slices"
)

// CurrentAssessmentRevision is the reviewed current delivery assessment.
const CurrentAssessmentRevision = "2026-10-31"

// retainedAssessments returns the immutable assessment revisions.
func retainedAssessments() []string { return []string{"2026-07-12", CurrentAssessmentRevision} }

const requiredDisposition = "required"

// CompletenessProfile maps each concern of one profile to its disposition.
type CompletenessProfile struct {
	ID           string
	Dispositions map[string]string
}

// CompletenessTaxonomy is one revision of the completeness taxonomy.
type CompletenessTaxonomy struct {
	ProfileFamily, Revision string
	Concerns                []string
	Profiles                []CompletenessProfile
}

// CompletenessAssessment is one retained delivery assessment. Statuses maps
// each concern to its delivery status.
type CompletenessAssessment struct {
	ProfileFamily, TaxonomyRevision, Revision string
	Statuses                                  map[string]string
}

// CompletenessResult is the outcome of one taxonomy profile.
type CompletenessResult struct {
	ProfileID        string
	Complete         bool
	BlockingConcerns []string
}

func (p *Profiles) decodeCompleteness(documents map[string][]byte) error {
	var taxonomy struct {
		ProfileFamily string `json:"profile_family"`
		Revision      string `json:"revision"`
		Concerns      []struct {
			ID string `json:"concern_id"`
		} `json:"concerns"`
		Profiles []struct {
			ID           string            `json:"profile_id"`
			Dispositions map[string]string `json:"dispositions"`
		} `json:"profiles"`
	}
	if err := decode(documents[pathTaxonomy], &taxonomy); err != nil {
		return err
	}
	p.taxonomy = CompletenessTaxonomy{ProfileFamily: taxonomy.ProfileFamily, Revision: taxonomy.Revision}
	for _, concern := range taxonomy.Concerns {
		p.taxonomy.Concerns = append(p.taxonomy.Concerns, concern.ID)
	}
	for _, profile := range taxonomy.Profiles {
		p.taxonomy.Profiles = append(p.taxonomy.Profiles, CompletenessProfile(profile))
	}
	p.assessments = map[string]CompletenessAssessment{}
	for _, revision := range retainedAssessments() {
		var wire struct {
			ProfileFamily    string `json:"profile_family"`
			TaxonomyRevision string `json:"taxonomy_revision"`
			Revision         string `json:"assessment_revision"`
			Concerns         []struct {
				ID     string `json:"concern_id"`
				Status string `json:"status"`
			} `json:"concerns"`
		}
		if err := decode(documents[completenessDir+"delivery-assessment-"+revision+".json"], &wire); err != nil {
			return err
		}
		if wire.Revision != revision {
			return damaged()
		}
		assessment := CompletenessAssessment{ProfileFamily: wire.ProfileFamily, TaxonomyRevision: wire.TaxonomyRevision, Revision: wire.Revision, Statuses: map[string]string{}}
		for _, concern := range wire.Concerns {
			assessment.Statuses[concern.ID] = concern.Status
		}
		p.assessments[revision] = assessment
	}
	return nil
}

// CompletenessTaxonomy returns the packaged taxonomy.
func (p *Profiles) CompletenessTaxonomy() CompletenessTaxonomy {
	taxonomy := p.taxonomy
	taxonomy.Concerns = slices.Clone(taxonomy.Concerns)
	taxonomy.Profiles = slices.Clone(taxonomy.Profiles)
	for i := range taxonomy.Profiles {
		taxonomy.Profiles[i].Dispositions = maps.Clone(taxonomy.Profiles[i].Dispositions)
	}
	return taxonomy
}

// CompletenessAssessment returns a retained assessment revision. An unknown
// revision is a NotFound fault.
func (p *Profiles) CompletenessAssessment(revision string) (CompletenessAssessment, error) {
	assessment, ok := p.assessments[revision]
	if !ok {
		return CompletenessAssessment{}, notFound("completeness-assessment-unknown")
	}
	assessment.Statuses = maps.Clone(assessment.Statuses)
	return assessment, nil
}

// EvaluateCompleteness joins one taxonomy to one assessment and reports each
// profile in taxonomy order. A profile is complete when each required
// concern is implemented or covered by an external contract. A join failure
// is an InvalidInput fault.
func EvaluateCompleteness(taxonomy CompletenessTaxonomy, assessment CompletenessAssessment) ([]CompletenessResult, error) {
	if assessment.ProfileFamily != taxonomy.ProfileFamily || assessment.TaxonomyRevision != taxonomy.Revision {
		return nil, invalid("completeness-join-mismatch")
	}
	concerns := map[string]bool{}
	for _, concern := range taxonomy.Concerns {
		concerns[concern] = true
	}
	if !maps.Equal(concerns, setOf(slices.Collect(maps.Keys(assessment.Statuses)))) {
		return nil, invalid("completeness-join-mismatch")
	}
	results := make([]CompletenessResult, 0, len(taxonomy.Profiles))
	for _, profile := range taxonomy.Profiles {
		if !maps.Equal(concerns, setOf(slices.Collect(maps.Keys(profile.Dispositions)))) {
			return nil, invalid("completeness-join-mismatch")
		}
		blocking := []string{}
		for _, concern := range slices.Sorted(maps.Keys(profile.Dispositions)) {
			status := assessment.Statuses[concern]
			if profile.Dispositions[concern] == requiredDisposition && status != "implemented" && status != "external-contract" {
				blocking = append(blocking, concern)
			}
		}
		results = append(results, CompletenessResult{ProfileID: profile.ID, Complete: len(blocking) == 0, BlockingConcerns: blocking})
	}
	return results, nil
}

func setOf(values []string) map[string]bool {
	result := make(map[string]bool, len(values))
	for _, value := range values {
		result[value] = true
	}
	return result
}
