package sdlrules

import "testing"

func TestDiagnosticQuotingMatchesPython314(t *testing.T) {
	for _, row := range []struct{ value, want string }{
		{"plain", `'plain'`},
		{"one'quote", `"one'quote"`},
		{"both'\"quotes", `'both\'"quotes'`},
		{"back\\slash\n\t\r", `'back\\slash\n\t\r'`},
		{"\u0085\u0378\u2028", `'\x85\u0378\u2028'`},
		{"café 😀", `'café 😀'`},
		{"\U0001f6d8", `'\U0001f6d8'`},
	} {
		if actual := quoted(row.value); actual != row.want {
			t.Errorf("quoted(%q)=%s; want %s", row.value, actual, row.want)
		}
	}
}
