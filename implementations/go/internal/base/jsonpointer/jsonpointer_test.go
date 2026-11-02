package jsonpointer

import (
	"slices"
	"testing"
)

func TestTokensRoundTripWithTheRFC6901Escapes(t *testing.T) {
	tests := []struct {
		tokens  []string
		pointer string
	}{
		{nil, ""},
		{[]string{""}, "/"},
		{[]string{"a/b", "m~n", "~1"}, "/a~1b/m~0n/~01"},
		{[]string{"items", "0"}, "/items/0"},
	}
	for _, test := range tests {
		if got := FromTokens(test.tokens); got != test.pointer {
			t.Errorf("FromTokens(%q) = %q, want %q", test.tokens, got, test.pointer)
		}
		if got := Tokens(test.pointer); !slices.Equal(got, test.tokens) {
			t.Errorf("Tokens(%q) = %q, want %q", test.pointer, got, test.tokens)
		}
	}
	if got := Tokens("ignored/a"); !slices.Equal(got, []string{"a"}) {
		t.Errorf(`Tokens("ignored/a") = %q, want ["a"]`, got)
	}
	if got := UnescapeToken("~01"); got != "~1" {
		t.Errorf(`UnescapeToken("~01") = %q, want "~1"`, got)
	}
}

func TestArrayIndexAcceptsOnlyTheCanonicalSpelling(t *testing.T) {
	tests := []struct {
		token  string
		length int
		index  int
		ok     bool
	}{
		{"0", 1, 0, true},
		{"9", 10, 9, true},
		{"10", 10, 0, false},
		{"01", 10, 0, false},
		{"", 10, 0, false},
		{"-1", 10, 0, false},
		{"１", 10, 0, false},
		{"99999999999999999999999", 10, 0, false},
		{"0", 0, 0, false},
	}
	for _, test := range tests {
		index, ok := ArrayIndex(test.token, test.length)
		if index != test.index || ok != test.ok {
			t.Errorf("ArrayIndex(%q, %d) = %d, %t, want %d, %t", test.token, test.length, index, ok, test.index, test.ok)
		}
	}
}
