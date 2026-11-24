package canonjson

import (
	"errors"
	"strings"
	"testing"

	"github.com/gowebpki/jcs"
)

// The expected texts are the output of the Python reference: rfc8785.dumps,
// and json.dumps with sort_keys=True, separators=(",", ":"), and the
// ensure_ascii setting of the column.
func TestFormsMatchThePythonReference(t *testing.T) {
	tests := []struct {
		input, jcs, ascii, unicode string
	}{
		{"1.0", "1", "1.0", "1.0"},
		{"1e16", "10000000000000000", "1e+16", "1e+16"},
		{"1e15", "1000000000000000", "1000000000000000.0", "1000000000000000.0"},
		{"0.0001", "0.0001", "0.0001", "0.0001"},
		{"0.00001", "0.00001", "1e-05", "1e-05"},
		{"-0.0", "0", "-0.0", "-0.0"},
		{"-0", "0", "0", "0"},
		{"1e-7", "1e-7", "1e-07", "1e-07"},
		{"-2.5e-7", "-2.5e-7", "-2.5e-07", "-2.5e-07"},
		{"123456789.123", "123456789.123", "123456789.123", "123456789.123"},
		{"1.5e300", "1.5e+300", "1.5e+300", "1.5e+300"},
		{"9007199254740991", "9007199254740991", "9007199254740991", "9007199254740991"},
		{"-9007199254740991", "-9007199254740991", "-9007199254740991", "-9007199254740991"},
		{"\"é\u2028😀\"", "\"é\u2028😀\"", `"\u00e9\u2028\ud83d\ude00"`, "\"é\u2028😀\""},
		{`"\u0000\u001f\u007f\"\\\/\b\f\n\r\t"`, `"\u0000\u001f` + "\x7f" + `\"\\/\b\f\n\r\t"`, `"\u0000\u001f\u007f\"\\/\b\f\n\r\t"`, `"\u0000\u001f` + "\x7f" + `\"\\/\b\f\n\r\t"`},
		{`{"b": 1, "a": [true, null, false], "a": "last"}`, `{"a":"last","b":1}`, `{"a":"last","b":1}`, `{"a":"last","b":1}`},
		{"{\"\ue000\": 1, \"😀\": 2}", "{\"😀\":2,\"\ue000\":1}", `{"\ue000":1,"\ud83d\ude00":2}`, "{\"\ue000\":1,\"😀\":2}"},
		{`" ~\uffff"`, "\" ~\uffff\"", `" ~\uffff"`, "\" ~\uffff\""},
		{`"\ud83d\ude00"`, `"😀"`, `"\ud83d\ude00"`, `"😀"`},
		{`"\ud800\udc00"`, "\"\U00010000\"", `"\ud800\udc00"`, "\"\U00010000\""},
		{`"\udbff\udfff"`, "\"\U0010ffff\"", `"\udbff\udfff"`, "\"\U0010ffff\""},
	}
	for _, test := range tests {
		for _, form := range []struct {
			name   string
			encode func([]byte) ([]byte, error)
			want   string
		}{
			{"JCS", JCS, test.jcs},
			{"Sorted(ascii)", func(data []byte) ([]byte, error) { return Sorted(data, true) }, test.ascii},
			{"Sorted(unicode)", func(data []byte) ([]byte, error) { return Sorted(data, false) }, test.unicode},
		} {
			got, err := form.encode([]byte(test.input))
			if err != nil {
				t.Errorf("%s(%s) error = %v", form.name, test.input, err)
				continue
			}
			if string(got) != form.want {
				t.Errorf("%s(%s) = %s, want %s", form.name, test.input, got, form.want)
			}
		}
	}
}

func TestJCSRefusesAnInexactInteger(t *testing.T) {
	for _, input := range []string{"9007199254740992", "-9007199254740992", `[{"a": 123456789012345678901234567890}]`} {
		if _, err := JCS([]byte(input)); !errors.Is(err, ErrInput) {
			t.Errorf("JCS(%s) error = %v, want ErrInput", input, err)
		}
	}
}

// The Python reference writes an integer with up to 4,300 digits, without the
// sign, and refuses a longer one.
func TestSortedKeepsThePythonIntegerDigitLimit(t *testing.T) {
	for _, input := range []string{"123456789012345678901234567890", "-" + strings.Repeat("9", 4300)} {
		for _, ascii := range []bool{true, false} {
			if got, err := Sorted([]byte(input), ascii); err != nil || string(got) != input {
				t.Errorf("Sorted(%d digits, %t) = %.20s, %v, want the integer", len(input), ascii, got, err)
			}
		}
	}
	for _, input := range []string{strings.Repeat("9", 4301), "-" + strings.Repeat("9", 4301)} {
		if _, err := Sorted([]byte(input), true); !errors.Is(err, ErrInput) {
			t.Errorf("Sorted(%d digits) error = %v, want ErrInput", len(input), err)
		}
	}
}

func TestFormsRefuseInputWithoutAnEncoding(t *testing.T) {
	tests := map[string]string{
		"overflowing float":      "1e400",
		"nested overflow":        `{"a": [-1e400]}`,
		"lone high surrogate":    `"\ud83d"`,
		"lone low surrogate":     `"\ude00"`,
		"high without low":       `"\ud83dx"`,
		"invalid UTF-8":          "\"\xff\"",
		"second value":           "[1, 2] 3",
		"not JSON":               "NaN",
		"empty":                  "",
		"surrogate pair, broken": `"\ud83dA"`,
		"surrogates apart":       `"\ud83d \ude00"`,
		"high after an escape":   `"\n\ud83d"`,
	}
	for name, input := range tests {
		for _, encode := range []func([]byte) ([]byte, error){JCS, func(data []byte) ([]byte, error) { return Sorted(data, false) }} {
			if _, err := encode([]byte(input)); !errors.Is(err, ErrInput) {
				t.Errorf("%s: encode(%q) error = %v, want ErrInput", name, input, err)
			}
		}
	}
}

func TestSortedPreservesSurrogateEscapes(t *testing.T) {
	for _, test := range []struct{ input, want string }{
		{`"\ud800"`, `"\ud800"`},
		{`"\uDFFF"`, `"\udfff"`},
		{`"\ud800x\udfff"`, `"\ud800x\udfff"`},
		{`"\ud800\ud800\udc00"`, `"\ud800\ud800\udc00"`},
		{`["\udc00", "\ufffd", "\\ud800", "\ud83d\ude00"]`, `["\udc00","\ufffd","\\ud800","\ud83d\ude00"]`},
		{`{"\ud800":1,"\ufffd":2,"\ud800":3,"😀":4,"\ue000":5}`, `{"\ud800":3,"\ue000":5,"\ufffd":2,"\ud83d\ude00":4}`},
		{`{"\ud83d\ude00":1,"😀":2}`, `{"\ud83d\ude00":2}`},
	} {
		got, err := Sorted([]byte(test.input), true)
		if err != nil || string(got) != test.want {
			t.Errorf("Sorted(%s, true) = %s, %v, want %s", test.input, got, err, test.want)
		}
	}
	for _, input := range []string{`{"\ud800":1}`, `["\udfff"]`, `"\ud800"`} {
		for _, encode := range []func([]byte) ([]byte, error){JCS, func(data []byte) ([]byte, error) { return Sorted(data, false) }} {
			if _, err := encode([]byte(input)); !errors.Is(err, ErrInput) {
				t.Errorf("encode(%s) error = %v, want ErrInput", input, err)
			}
		}
	}
}

func TestDiscardedMembersKeepPythonDecodeBehavior(t *testing.T) {
	for _, encode := range []func([]byte) ([]byte, error){JCS,
		func(data []byte) ([]byte, error) { return Sorted(data, true) },
		func(data []byte) ([]byte, error) { return Sorted(data, false) },
	} {
		input := []byte(`{"a":"\ud800","a":1}`)
		if got, err := encode(input); err != nil || string(got) != `{"a":1}` {
			t.Errorf("encode(%s) = %s, %v, want {a:1}", input, got, err)
		}
		input = []byte(`{"a":` + strings.Repeat("9", 4301) + `,"a":1}`)
		if _, err := encode(input); !errors.Is(err, ErrInput) {
			t.Errorf("encode(discarded long integer) error = %v, want ErrInput", err)
		}
	}
}

func TestFormsKeepNestingLimit(t *testing.T) {
	input := []byte(strings.Repeat("[", 10001) + "0" + strings.Repeat("]", 10001))
	if _, err := Sorted(input, true); !errors.Is(err, ErrInput) {
		t.Errorf("Sorted(deep array) error = %v, want ErrInput", err)
	}
}

// FuzzForms checks that each sorted form is idempotent and that each JCS text
// is canonical for the RFC 8785 transform. JCS itself is not idempotent: it
// writes the float 1e16 as an integer, which it then refuses as an integer
// outside the exact range.
func FuzzForms(f *testing.F) {
	for _, seed := range []string{`{"b": [1, 2.5e-7, "é"], "a": null}`, "1e16", `"😀"`, "-0.0", `"\ud800"`, `{"\udfff": "\ufffd"}`} {
		f.Add([]byte(seed))
	}
	f.Fuzz(func(t *testing.T, data []byte) {
		for _, ascii := range []bool{true, false} {
			once, err := Sorted(data, ascii)
			if err != nil {
				continue
			}
			if twice, err := Sorted(once, ascii); err != nil || string(twice) != string(once) {
				t.Errorf("Sorted(%q, %t) = %q, %v, want the same text", once, ascii, twice, err)
			}
		}
		canonical, err := JCS(data)
		if err != nil {
			return
		}
		if again, err := jcs.Transform(canonical); err != nil || string(again) != string(canonical) {
			t.Errorf("jcs.Transform(%q) = %q, %v, want the same text", canonical, again, err)
		}
	})
}
