// Package fault owns the six operational error categories of ADR-116.
// Error text contains a stable code, never the cause's message or payload.
package fault

import (
	"errors"
	"strings"
)

// Category describes what went wrong, independently of a subsystem.
type Category uint8

// The closed operational categories.
const (
	InvalidInput Category = iota + 1
	Conflict
	NotFound
	Authorization
	Operational
	EvidenceIntegrity
)

// ErrDefinition reports a programming error in an error definition.
var ErrDefinition = errors.New("fault: invalid error definition")

// Error is a classified error with a stable code and an optional wrapped cause.
type Error struct {
	category Category
	code     string
	cause    error
}

// New constructs an error. An invalid category or code gives ErrDefinition.
// Codes start with a lowercase ASCII letter, contain lowercase letters,
// digits or hyphens, and have at most 64 bytes.
func New(category Category, code string, cause error) error {
	if category < InvalidInput || category > EvidenceIntegrity || !validCode(code) {
		return ErrDefinition
	}
	return &Error{category: category, code: code, cause: cause}
}

func validCode(code string) bool {
	return len(code) > 0 && len(code) <= 64 && code[0] >= 'a' && code[0] <= 'z' &&
		strings.Trim(code, "abcdefghijklmnopqrstuvwxyz0123456789-") == ""
}

func (e *Error) Error() string { return e.category.String() + ": " + e.code }

// Category returns the operational category.
func (e *Error) Category() Category { return e.category }

// Code returns the stable value-free code.
func (e *Error) Code() string { return e.code }

// Unwrap preserves standard errors.Is and errors.As traversal.
func (e *Error) Unwrap() error { return e.cause }

func (c Category) String() string {
	switch c {
	case InvalidInput:
		return "invalid-input"
	case Conflict:
		return "conflict"
	case NotFound:
		return "not-found"
	case Authorization:
		return "authorization"
	case Operational:
		return "operational"
	case EvidenceIntegrity:
		return "evidence-integrity"
	default:
		return "unknown"
	}
}

// CategoryOf finds the nearest classified error in a standard error chain.
func CategoryOf(err error) (Category, bool) {
	if classified, ok := errors.AsType[interface {
		error
		Category() Category
	}](err); ok {
		category := classified.Category()
		return category, category >= InvalidInput && category <= EvidenceIntegrity
	}
	return 0, false
}
