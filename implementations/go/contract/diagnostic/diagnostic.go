// Package diagnostic defines the structured result records that contract,
// SDL and processor operations return. A record carries machine-readable
// codes and locations; its message never repeats a supplied value.
package diagnostic

import "github.com/OpenRAE/rae/implementations/go/base/fault"

// Range is a one-based source range. A zero Range means that the source has
// no line and column positions.
type Range struct{ StartLine, StartColumn, EndLine, EndColumn int }

// Diagnostic is one machine-readable finding. Code, Domain and Address
// identify the finding; Message is fixed text for a reader.
type Diagnostic struct {
	Code, Severity, Stage, Source, Pointer, Message, Domain, Address string
	Range                                                            *Range
}

// Error is an operation failure that also carries its diagnostics. Its
// category is one of the value-free fault categories.
type Error interface {
	error
	Code() string
	Category() fault.Category
	Diagnostics() []Diagnostic
	Unwrap() error
}
