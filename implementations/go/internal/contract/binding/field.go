// Package binding holds schema-derived transport values. These values do not
// prove semantic validity. The validation owner admits external payloads first.
package binding

import "encoding/json"

// Field preserves the distinction between an absent member, null and a value.
// Its zero value is absent. JSON object fields use the omitzero option.
type Field[T any] struct {
	present bool
	value   *T
}

// IsZero reports whether the member is absent.
func (f Field[T]) IsZero() bool { return !f.present }

// Present reports whether the member was supplied, including explicit null.
func (f Field[T]) Present() bool { return f.present }

// Null reports whether the member was explicitly null.
func (f Field[T]) Null() bool { return f.present && f.value == nil }

// Value returns the supplied transport value. False means absent or null.
//
//nolint:ireturn // Each generated instantiation returns its concrete transport type; no runtime interface is returned.
func (f Field[T]) Value() (T, bool) {
	if f.value != nil {
		return *f.value, true
	}
	var zero T
	return zero, false
}

// UnmarshalJSON decodes a supplied member without inserting defaults.
func (f *Field[T]) UnmarshalJSON(data []byte) error {
	var value *T
	if err := json.Unmarshal(data, &value); err != nil {
		return err
	}
	f.present, f.value = true, value
	return nil
}

// MarshalJSON returns null or the supplied value. The containing object omits
// absent members through IsZero.
func (f Field[T]) MarshalJSON() ([]byte, error) { return json.Marshal(f.value) }
