package admission

import (
	"bytes"
	"encoding/json"
)

// RealizationConstraintBinding binds the admitted authority and safe source
// projection under the default relation limits. The digest grants no support
// or execution authority.
func RealizationConstraintBinding(constraint, source Fragment) (string, error) {
	return RealizationConstraintBindingWithLimits(constraint, source, DefaultConstraintLimits())
}

// RealizationConstraintBindingWithLimits binds both halves of a template after
// it admits the authority and the source projection under the caller's limits.
func RealizationConstraintBindingWithLimits(constraint, source Fragment, limits ConstraintLimits) (string, error) {
	owned, err := nativeFragment(constraint, RealizationConstraint)
	if err != nil || CheckFragment(source, RealizationValue) != nil {
		return "", fragmentInvalid()
	}
	var document constraintDocument
	decoder := json.NewDecoder(bytes.NewReader(owned.data))
	decoder.UseNumber()
	if err := decoder.Decode(&document); err != nil {
		return "", fragmentInvalid()
	}
	if !admitConstraintWork(document, object(owned.Document()), limits) {
		return "", fragmentInvalid()
	}
	admitted, err := ValidateRealizationValue(source, limits)
	if err != nil {
		return "", err
	}
	if stringAt(admitted.Document(), "status") != assuranceConformant {
		return "", fragmentInvalid()
	}
	return jsonDigest(map[string]any{termConstraint: constraint.Document(), "source": source.Document()})
}
