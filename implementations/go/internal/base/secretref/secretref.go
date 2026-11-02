// Package secretref validates logical identifiers of operator-managed secret
// references. It never reads or resolves secret material.
package secretref

import "github.com/OpenRAE/rae/implementations/go/internal/base/fault"

// ErrID reports an invalid logical secret-reference identifier.
var ErrID = fault.New(fault.InvalidInput, "secret-reference", nil)

// Valid implements [a-z][a-z0-9]*(?:[._-][a-z0-9]+)*, with 1..256 bytes.
func Valid(id string) bool {
	if len(id) == 0 || len(id) > 256 || id[0] < 'a' || id[0] > 'z' {
		return false
	}
	separator := false
	for _, ch := range id {
		if ch >= 'a' && ch <= 'z' || ch >= '0' && ch <= '9' {
			separator = false
			continue
		}
		if separator || ch != '.' && ch != '_' && ch != '-' {
			return false
		}
		separator = true
	}
	return !separator
}

// Validate checks a logical identifier without including it in a refusal.
func Validate(id string) error {
	if !Valid(id) {
		return ErrID
	}
	return nil
}
