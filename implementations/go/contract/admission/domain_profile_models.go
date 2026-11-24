package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/domainprofile"

// domainProfileModel applies the shared domain-profile model rules.
func (e *Validator) domainProfileModel(name string, v any) (bool, error) {
	known, err := domainprofile.CheckModel(name, v)
	if err != nil {
		return true, invalid()
	}
	return known, nil
}
