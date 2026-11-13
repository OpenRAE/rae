package admission

import (
	"bytes"
	"encoding/json"
)

// RealizationConstraintBinding binds the admitted authority and safe source
// projection. The digest grants no support or execution authority.
func RealizationConstraintBinding(constraint, source Fragment) (string, error) {
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
	if !admitConstraintWork(document, object(owned.Document()), DefaultConstraintLimits()) {
		return "", fragmentInvalid()
	}
	return jsonDigest(map[string]any{termConstraint: constraint.Document(), "source": source.Document()})
}
