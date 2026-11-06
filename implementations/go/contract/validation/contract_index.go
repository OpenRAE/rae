package validation

// HasContract reports membership in the compiled publication inventory.
// It grants no schema verdict or semantic admission.
func (v *Validator) HasContract(id string) bool { return v != nil && v.contracts[id].schema != nil }
