// Package canonjson encodes a JSON value in the two canonical forms of RAES
// digests (Go port 06, issue #1779).
//
// [JCS] is the RFC 8785 JSON Canonicalization Scheme, the form of contract
// digests. [Sorted] is the form that Python's json.dumps writes with sorted
// keys and the separators "," and ":". Older digests, stored records, and the
// schema content hashes use it. The two forms differ, for example in number
// notation and in key order.
//
// Both functions take UTF-8 JSON text that holds one value. A later duplicate
// member replaces an earlier one, as in Python. Both refuse a UTF-16
// surrogate escape that is not part of a pair. Valid UTF-8 cannot hold such a
// surrogate, and I-JSON (RFC 7493) forbids it. Python's RFC 8785 form and its
// form without ensure_ascii also refuse it, but its ensure_ascii form writes it
// back as an escape.
package canonjson

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"math"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"

	"github.com/gowebpki/jcs"
)

// ErrInput reports JSON text that a canonical form cannot encode.
var ErrInput = errors.New("canonjson: the input has no canonical encoding")

const (
	// maxExact is 2^53 - 1, the largest magnitude of an integer that RFC 8785
	// encodes exactly.
	maxExact = 9_007_199_254_740_991
	// maxDigits is the largest number of digits of an integer that Python
	// converts to text (sys.int_info.default_max_str_digits).
	maxDigits = 4300
)

// JCS returns the RFC 8785 form of the JSON value in data. Like the Python
// rfc8785 package, it refuses an integer with a magnitude above 2^53 - 1,
// because RFC 8785 gives it no exact value. It also refuses a number outside
// the finite float64 range.
func JCS(data []byte) ([]byte, error) {
	compact, err := encode(data, false, jcsNumber)
	if err != nil {
		return nil, err
	}
	canonical, err := jcs.Transform(compact)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInput, err)
	}
	return canonical, nil
}

// Sorted returns the JSON value in data as Python's json.dumps writes it with
// sort_keys=True and separators=(",", ":"). With ascii, it escapes each
// character outside printable ASCII, as ensure_ascii=True does. It refuses a
// number outside the finite float64 range, as allow_nan=False does, and an
// integer with more than 4,300 digits, as Python does.
func Sorted(data []byte, ascii bool) ([]byte, error) {
	return encode(data, ascii, pythonNumber)
}

// encode writes the JSON value in data with sorted keys, compact separators,
// and the string escapes of Python's json module. The number function gives
// the text of each number.
func encode(data []byte, ascii bool, number func(json.Number) (string, error)) ([]byte, error) {
	value, err := decode(data)
	if err != nil {
		return nil, err
	}
	e := encoder{ascii: ascii, number: number}
	if err := e.value(value); err != nil {
		return nil, err
	}
	return e.out.Bytes(), nil
}

// decode returns the single JSON value in data, with numbers as their text.
func decode(data []byte) (any, error) {
	if !utf8.Valid(data) || hasLoneSurrogate(data) {
		return nil, fmt.Errorf("%w: the text is not valid Unicode", ErrInput)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInput, err)
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, fmt.Errorf("%w: data follows the value", ErrInput)
	}
	return value, nil
}

// escapes matches one escape of a JSON string. Group 1 holds the four
// hexadecimal digits of a \u escape.
var escapes = regexp.MustCompile(`\\(?:u([0-9a-fA-F]{4})|.)`)

// hasLoneSurrogate reports whether a string escape in the JSON text data names
// a UTF-16 surrogate that is not part of a pair. A pair is a \u escape of a
// high surrogate directly followed by a \u escape of a low surrogate. The Go
// decoder would replace a lone surrogate with U+FFFD, and so give two
// different texts the same encoding.
func hasLoneSurrogate(data []byte) bool {
	found := escapes.FindAllSubmatchIndex(data, -1)
	for i := 0; i < len(found); i++ {
		unit := escapedUnit(data, found[i])
		if !utf16.IsSurrogate(unit) {
			continue
		}
		if i+1 == len(found) || found[i+1][0] != found[i][1] ||
			utf16.DecodeRune(unit, escapedUnit(data, found[i+1])) == utf8.RuneError {
			return true
		}
		i++ // The low surrogate of the pair.
	}
	return false
}

// escapedUnit returns the UTF-16 code unit of a \u escape that escapes found.
// For another escape it returns zero, which is not a surrogate.
func escapedUnit(data []byte, match []int) rune {
	if match[2] == -1 {
		return 0
	}
	// The pattern admits exactly four hexadecimal digits, so the text parses.
	unit, _ := strconv.ParseUint(string(data[match[2]:match[3]]), 16, 16)
	return rune(unit)
}

// encoder writes a decoded JSON value with sorted keys and compact separators.
type encoder struct {
	out bytes.Buffer
	// ascii selects the escape of each character outside printable ASCII.
	ascii bool
	// number returns the text of a number, or an error when the form has no
	// text for it.
	number func(json.Number) (string, error)
}

// value writes a decoded JSON value.
func (e *encoder) value(decoded any) error {
	switch v := decoded.(type) {
	case nil:
		e.out.WriteString("null")
	case bool:
		e.out.WriteString(strconv.FormatBool(v))
	case string:
		e.quote(v)
	case json.Number:
		text, err := e.number(v)
		if err != nil {
			return err
		}
		e.out.WriteString(text)
	case []any:
		e.out.WriteByte('[')
		for i, item := range v {
			if i > 0 {
				e.out.WriteByte(',')
			}
			if err := e.value(item); err != nil {
				return err
			}
		}
		e.out.WriteByte(']')
	case map[string]any:
		return e.object(v)
	}
	return nil
}

// object writes the members of an object in code point order of their keys.
// The byte order of UTF-8 text is its code point order.
func (e *encoder) object(members map[string]any) error {
	e.out.WriteByte('{')
	for i, key := range slices.Sorted(maps.Keys(members)) {
		if i > 0 {
			e.out.WriteByte(',')
		}
		e.quote(key)
		e.out.WriteByte(':')
		if err := e.value(members[key]); err != nil {
			return err
		}
	}
	e.out.WriteByte('}')
	return nil
}

// quote writes s as a JSON string with the escapes of Python's json module.
func (e *encoder) quote(s string) {
	e.out.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			e.out.WriteString(`\"`)
		case '\\':
			e.out.WriteString(`\\`)
		case '\n':
			e.out.WriteString(`\n`)
		case '\r':
			e.out.WriteString(`\r`)
		case '\t':
			e.out.WriteString(`\t`)
		case '\b':
			e.out.WriteString(`\b`)
		case '\f':
			e.out.WriteString(`\f`)
		default:
			e.char(r)
		}
	}
	e.out.WriteByte('"')
}

// char writes a control character, and with ascii a character outside
// printable ASCII, as \u escapes of its UTF-16 code units. It writes each other
// character as it is.
func (e *encoder) char(r rune) {
	if r >= 0x20 && (!e.ascii || r <= 0x7e) {
		e.out.WriteRune(r)
		return
	}
	units := []rune{r}
	if r > 0xffff {
		high, low := utf16.EncodeRune(r)
		units = []rune{high, low}
	}
	for _, unit := range units {
		fmt.Fprintf(&e.out, `\u%04x`, unit)
	}
}

// jcsNumber returns the text of a JSON number that RFC 8785 encodes exactly:
// an integer with a magnitude up to 2^53 - 1, or a finite float.
func jcsNumber(n json.Number) (string, error) {
	if !isInteger(n) {
		if _, err := parseFloat(n); err != nil {
			return "", err
		}
		return string(n), nil
	}
	value, err := strconv.ParseInt(string(n), 10, 64)
	if err != nil || value > maxExact || value < -maxExact {
		return "", fmt.Errorf("%w: an integer is outside the exact range of RFC 8785", ErrInput)
	}
	return string(n), nil
}

// pythonNumber returns a JSON number as Python's json module writes it: an
// integer in decimal, and a float as repr(float) writes it.
func pythonNumber(n json.Number) (string, error) {
	if !isInteger(n) {
		f, err := parseFloat(n)
		if err != nil {
			return "", err
		}
		return pythonFloat(f), nil
	}
	digits := strings.TrimPrefix(string(n), "-")
	if len(digits) > maxDigits {
		return "", fmt.Errorf("%w: an integer has more than %d digits", ErrInput, maxDigits)
	}
	// JSON integer text has no plus sign and no leading zero, so it is the
	// decimal form of Python, except -0, which Python reads as 0.
	if digits == "0" {
		return "0", nil
	}
	return string(n), nil
}

// isInteger reports whether Python reads the JSON number n as an int.
func isInteger(n json.Number) bool {
	return !strings.ContainsAny(string(n), ".eE")
}

// parseFloat returns the float64 of a JSON number, or an error when the number
// is outside the finite range. The decoder checked the syntax, so a range error
// is the only error.
func parseFloat(n json.Number) (float64, error) {
	f, err := strconv.ParseFloat(string(n), 64)
	if err != nil {
		return 0, fmt.Errorf("%w: a number is outside the finite float64 range", ErrInput)
	}
	return f, nil
}

// pythonFloat formats f as Python's repr(float) does: the shortest digits that
// read back as f, in fixed notation for decimal exponents from -4 to 15 and in
// scientific notation otherwise.
func pythonFloat(f float64) string {
	sign := ""
	if math.Signbit(f) {
		sign = "-"
	}
	if f == 0 {
		return sign + "0.0"
	}
	mantissa, exponentText, _ := strings.Cut(strconv.FormatFloat(math.Abs(f), 'e', -1, 64), "e")
	exponent, _ := strconv.Atoi(exponentText)
	digits := strings.Replace(mantissa, ".", "", 1)
	if exponent < -4 || exponent >= 16 {
		if len(digits) > 1 {
			digits = digits[:1] + "." + digits[1:]
		}
		return fmt.Sprintf("%s%se%+03d", sign, digits, exponent)
	}
	if exponent < 0 {
		return sign + "0." + strings.Repeat("0", -exponent-1) + digits
	}
	if len(digits) <= exponent+1 {
		return sign + digits + strings.Repeat("0", exponent+1-len(digits)) + ".0"
	}
	return sign + digits[:exponent+1] + "." + digits[exponent+1:]
}
