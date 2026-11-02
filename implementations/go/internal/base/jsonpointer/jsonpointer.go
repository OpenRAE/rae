// Package jsonpointer converts RFC 6901 JSON Pointer reference tokens (Go
// port 06, issue #1779).
//
// The pointer "" names the whole document, and the pointer "/" names the member
// with the empty name. These functions convert tokens only; callers keep their
// own pointer validation and resolution rules.
package jsonpointer

import (
	"strconv"
	"strings"
)

// EscapeToken encodes one reference token: "~" becomes "~0", then "/" becomes
// "~1" (RFC 6901 section 3).
func EscapeToken(token string) string {
	return strings.ReplaceAll(strings.ReplaceAll(token, "~", "~0"), "/", "~1")
}

// UnescapeToken decodes one reference token: "~1" becomes "/", then "~0"
// becomes "~" (RFC 6901 section 4), so "~01" decodes to "~1".
func UnescapeToken(token string) string {
	return strings.ReplaceAll(strings.ReplaceAll(token, "~1", "/"), "~0", "~")
}

// FromTokens joins reference tokens into a pointer. No tokens give the
// whole-document pointer "".
func FromTokens(tokens []string) string {
	var pointer strings.Builder
	for _, token := range tokens {
		pointer.WriteByte('/')
		pointer.WriteString(EscapeToken(token))
	}
	return pointer.String()
}

// Tokens splits a pointer into decoded reference tokens. Text before the first
// "/" is ignored.
func Tokens(pointer string) []string {
	parts := strings.Split(pointer, "/")[1:]
	for i, part := range parts {
		parts[i] = UnescapeToken(part)
	}
	return parts
}

// IsArrayIndex reports whether a token has the canonical array-index form: "0",
// or ASCII digits without a leading zero. Each list position thus has one
// spelling, and "/items/01" never aliases "/items/1".
func IsArrayIndex(token string) bool {
	if token == "" || strings.Trim(token, "0123456789") != "" {
		return false
	}
	return len(token) == 1 || token[0] != '0'
}

// ArrayIndex returns the list position that a token names in a list of length
// elements, and false when it names none.
func ArrayIndex(token string, length int) (int, bool) {
	if !IsArrayIndex(token) || len(token) > len(strconv.Itoa(length)) {
		return 0, false
	}
	index, err := strconv.Atoi(token)
	if err != nil || index >= length {
		return 0, false
	}
	return index, true
}
