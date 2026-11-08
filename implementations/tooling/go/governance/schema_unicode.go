package governance

import (
	"unicode"

	"golang.org/x/text/unicode/rangetable"
)

// Assignment data remains shared by numeric, identifier and format checks.
func pythonAssigned() *unicode.RangeTable { return rangetable.Assigned("16.0.0") }
