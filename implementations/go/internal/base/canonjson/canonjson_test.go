package canonjson

import (
	"errors"
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
		{"\"é\u2028😀\"", "\"é\u2028😀\"", `"\u00e9\u2028\ud83d\ude00"`, "\"é\u2028😀\""},
		{`"\u0000\u001f\u007f\"\\\/\b\f\n\r\t"`, `"\u0000\u001f` + "\x7f" + `\"\\/\b\f\n\r\t"`, `"\u0000\u001f\u007f\"\\/\b\f\n\r\t"`, `"\u0000\u001f` + "\x7f" + `\"\\/\b\f\n\r\t"`},
		{`{"b": 1, "a": [true, null, false], "a": "last"}`, `{"a":"last","b":1}`, `{"a":"last","b":1}`, `{"a":"last","b":1}`},
		{"{\"\ue000\": 1, \"😀\": 2}", "{\"😀\":2,\"\ue000\":1}", `{"\ue000":1,"\ud83d\ude00":2}`, "{\"\ue000\":1,\"😀\":2}"},
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
	got, err := Sorted([]byte("123456789012345678901234567890"), true)
	if err != nil || string(got) != "123456789012345678901234567890" {
		t.Errorf("Sorted(big integer) = %s, %v, want the integer", got, err)
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
	}
	for name, input := range tests {
		for _, encode := range []func([]byte) ([]byte, error){JCS, func(data []byte) ([]byte, error) { return Sorted(data, true) }} {
			if _, err := encode([]byte(input)); !errors.Is(err, ErrInput) {
				t.Errorf("%s: encode(%q) error = %v, want ErrInput", name, input, err)
			}
		}
	}
}

func TestEscapesThatAreNotSurrogatesStayValid(t *testing.T) {
	for _, input := range []string{`"\\ud83d"`, `"é\u"`, `"\"`, `"\uZZZZ"`} {
		if hasLoneSurrogate([]byte(input)) {
			t.Errorf("hasLoneSurrogate(%s) = true, want false", input)
		}
	}
}

// FuzzForms checks that each sorted form is idempotent and that each JCS text
// is canonical for the RFC 8785 transform. JCS itself is not idempotent: it
// writes a float of 1e16 as an integer, which RFC 8785 then refuses.
func FuzzForms(f *testing.F) {
	for _, seed := range []string{`{"b": [1, 2.5e-7, "é"], "a": null}`, "1e16", `"😀"`, "-0.0"} {
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
