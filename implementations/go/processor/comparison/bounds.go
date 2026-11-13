package comparison

import (
	"encoding/json"
	"unicode/utf8"
)

// wireBudget refuses aggregate output before the JSON encoder allocates it.
// Fixed record charges cover field names and punctuation; scalar charges use
// their actual escaped encoding. The private compiler has no arbitrary carrier.
type wireBudget struct{ remaining, visits int }

func (b *wireBudget) record(overhead int, texts ...string) error {
	b.remaining -= overhead
	b.visits++
	if b.remaining < 0 || b.visits > 100000 {
		return invalid()
	}
	for _, text := range texts {
		if !utf8.ValidString(text) || len(text) > 1<<20 {
			return invalid()
		}
		raw, err := json.Marshal(text)
		if err != nil {
			return invalid()
		}
		b.remaining -= len(raw)
		if b.remaining < 0 {
			return invalid()
		}
	}
	return nil
}
func (b *wireBudget) coordinate(input coordinate) error {
	return b.record(512, input.Kind, input.Phase, input.Identity, input.Canonicalization, input.Digest, input.SourceProfile, input.ProvenanceProfile, input.Schema, input.ScenarioID, input.ScenarioVersion, input.ModuleID, input.ModuleVersion, input.TaskID, input.TaskVersion, input.RunID, input.RunVersion, input.CaptureID, input.SpecVersion, input.StudyID, input.StudyVersion, input.BindingID, input.BindingVersion)
}
func (b *wireBudget) scope(input scope) error {
	if err := b.record(256, input.ID, input.Policy, input.Status, input.Digest); err != nil {
		return err
	}
	if err := b.record(0, input.Roots...); err != nil {
		return err
	}
	for _, side := range [][]coordinate{input.Before, input.After} {
		for _, item := range side {
			if err := b.coordinate(item); err != nil {
				return err
			}
		}
	}
	return nil
}
func boundResult(input result) error {
	budget := wireBudget{remaining: 8 << 20}
	if err := budget.record(1024, input.Schema, input.Profile, input.ProfileDigest, input.Analyzer, input.RequestDigest, input.ScopeDigest, input.Completeness); err != nil {
		return err
	}
	if err := budget.scope(input.Scope); err != nil {
		return err
	}
	for _, item := range []coordinate{input.Before, input.After} {
		if err := budget.coordinate(item); err != nil {
			return err
		}
	}
	for _, item := range input.Changes {
		if err := budget.change(item); err != nil {
			return err
		}
	}
	for _, item := range input.Dependencies {
		if err := budget.dependency(item); err != nil {
			return err
		}
	}
	for _, item := range input.Paths {
		if err := budget.path(item); err != nil {
			return err
		}
	}
	return budget.record(256, append(append([]string{}, input.Reasons...), input.Context...)...)
}
func (b *wireBudget) change(input change) error {
	if err := b.record(512, input.Identity, stringValue(input.Before), stringValue(input.After), input.IdentityRelation, input.Textual, input.Structural, input.Semantic); err != nil {
		return err
	}
	return b.record(0, input.Reasons...)
}
func (b *wireBudget) dependency(input dependencyChange) error {
	if err := b.record(256, input.Dependent, input.Rule, input.Version, input.Relation); err != nil {
		return err
	}
	for _, state := range []*dependencyState{input.Before, input.After} {
		if state == nil {
			continue
		}
		if err := b.record(256, append(append([]string{state.Identity, state.Resolution}, state.Provenance...), state.Reasons...)...); err != nil {
			return err
		}
	}
	return nil
}
func (b *wireBudget) path(input impactPath) error {
	if err := b.record(128, input.Source, input.Affected); err != nil {
		return err
	}
	for _, step := range input.Steps {
		if err := b.record(256, step.Dependent, step.Dependency, step.Rule, step.Version, step.Side); err != nil {
			return err
		}
	}
	return nil
}
