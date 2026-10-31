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
// surrogate escape that is not part of a pair, because the Go decoder would
// replace it and so give two different texts the same encoding.
package canonjson

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"maps"
	"math"
	"math/big"
	"slices"
	"strconv"
	"strings"
	"unicode/utf16"
	"unicode/utf8"

	"github.com/gowebpki/jcs"
)

// ErrInput reports JSON text that a canonical form cannot encode.
var ErrInput = errors.New("canonjson: the input has no canonical encoding")

// maxExact is the largest magnitude of an integer that RFC 8785 encodes exactly.
const maxExact = 1<<53 - 1

// JCS returns the RFC 8785 form of the JSON value in data. It refuses an
// integer with a magnitude above 2^53 - 1 and a number outside the finite
// float64 range, as RFC 8785 requires.
func JCS(data []byte) ([]byte, error) {
	value, err := decode(data)
	if err != nil {
		return nil, err
	}
	if err = checkJCSNumbers(value); err != nil {
		return nil, err
	}
	// Marshal keeps the last duplicate member, and the transform then
	// canonicalizes the text.
	compact, err := json.Marshal(value)
	if err != nil {
		return nil, fmt.Errorf("%w: %w", ErrInput, err)
	}
	return jcs.Transform(compact)
}

// Sorted returns the JSON value in data as Python's json.dumps writes it with
// sort_keys=True and separators=(",", ":"). With ascii, it escapes each
// character outside printable ASCII, as ensure_ascii=True does. It refuses a
// number outside the finite float64 range, as allow_nan=False does.
func Sorted(data []byte, ascii bool) ([]byte, error) {
	value, err := decode(data)
	if err != nil {
		return nil, err
	}
	var out bytes.Buffer
	if err := writeSorted(&out, value, ascii); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
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

// hasLoneSurrogate reports whether a string escape in the JSON text data names
// a UTF-16 surrogate that is not part of a pair.
func hasLoneSurrogate(data []byte) bool {
	wantLow := false
	for i := 0; i < len(data); {
		unit, size := escape(data[i:])
		isLow := size == 6 && unit >= 0xdc00 && unit <= 0xdfff
		if wantLow != isLow {
			return true
		}
		wantLow = size == 6 && unit >= 0xd800 && unit <= 0xdbff
		i += max(size, 1)
	}
	return wantLow
}

// escape returns the UTF-16 code unit of a \u escape at the start of data, and
// the length of the escape. The length is zero when data does not start with
// an escape.
func escape(data []byte) (unit uint16, size int) {
	if len(data) < 2 || data[0] != '\\' {
		return 0, 0
	}
	if data[1] != 'u' || len(data) < 6 {
		return 0, 2
	}
	value, err := strconv.ParseUint(string(data[2:6]), 16, 16)
	if err != nil {
		return 0, 2
	}
	return uint16(value), 6
}

// checkJCSNumbers refuses each number in value that RFC 8785 cannot encode
// exactly.
func checkJCSNumbers(value any) error {
	switch v := value.(type) {
	case json.Number:
		return checkJCSNumber(v)
	case []any:
		return checkEach(v)
	case map[string]any:
		return checkEach(slices.Collect(maps.Values(v)))
	}
	return nil
}

func checkEach(values []any) error {
	for _, value := range values {
		if err := checkJCSNumbers(value); err != nil {
			return err
		}
	}
	return nil
}

// checkJCSNumber refuses an integer with a magnitude above 2^53 - 1 and a
// float outside the finite range.
func checkJCSNumber(n json.Number) error {
	if !isInteger(n) {
		_, err := parseFloat(n)
		return err
	}
	// The decoder checked the syntax, so the text always parses.
	value, _ := new(big.Int).SetString(string(n), 10)
	if value.CmpAbs(big.NewInt(maxExact)) > 0 {
		return fmt.Errorf("%w: the integer %s is outside the exact range", ErrInput, n)
	}
	return nil
}

func writeSorted(out *bytes.Buffer, value any, ascii bool) error {
	switch v := value.(type) {
	case nil:
		out.WriteString("null")
	case bool:
		out.WriteString(strconv.FormatBool(v))
	case string:
		writeString(out, v, ascii)
	case json.Number:
		text, err := pythonNumber(v)
		if err != nil {
			return err
		}
		out.WriteString(text)
	case []any:
		out.WriteByte('[')
		for i, item := range v {
			if i > 0 {
				out.WriteByte(',')
			}
			if err := writeSorted(out, item, ascii); err != nil {
				return err
			}
		}
		out.WriteByte(']')
	case map[string]any:
		return writeObject(out, v, ascii)
	}
	return nil
}

// writeObject writes the members of an object in code point order of their
// keys. The byte order of UTF-8 text is its code point order.
func writeObject(out *bytes.Buffer, object map[string]any, ascii bool) error {
	keys := make([]string, 0, len(object))
	for key := range object {
		keys = append(keys, key)
	}
	slices.Sort(keys)
	out.WriteByte('{')
	for i, key := range keys {
		if i > 0 {
			out.WriteByte(',')
		}
		writeString(out, key, ascii)
		out.WriteByte(':')
		if err := writeSorted(out, object[key], ascii); err != nil {
			return err
		}
	}
	out.WriteByte('}')
	return nil
}

// writeString writes s with the escapes of Python's json module.
func writeString(out *bytes.Buffer, s string, ascii bool) {
	out.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			out.WriteString(`\"`)
		case '\\':
			out.WriteString(`\\`)
		case '\n':
			out.WriteString(`\n`)
		case '\r':
			out.WriteString(`\r`)
		case '\t':
			out.WriteString(`\t`)
		case '\b':
			out.WriteString(`\b`)
		case '\f':
			out.WriteString(`\f`)
		default:
			writeRune(out, r, ascii)
		}
	}
	out.WriteByte('"')
}

// writeRune writes a control character, and with ascii a character outside
// printable ASCII, as \u escapes of its UTF-16 code units.
func writeRune(out *bytes.Buffer, r rune, ascii bool) {
	if r >= 0x20 && (!ascii || r <= 0x7e) {
		out.WriteRune(r)
		return
	}
	units := []rune{r}
	if r > 0xffff {
		high, low := utf16.EncodeRune(r)
		units = []rune{high, low}
	}
	for _, unit := range units {
		fmt.Fprintf(out, `\u%04x`, unit)
	}
}

// pythonNumber returns a JSON number as Python's json module writes it: an
// integer in decimal, and a float as repr(float) writes it.
func pythonNumber(n json.Number) (string, error) {
	if isInteger(n) {
		// The decoder checked the syntax, so the text always parses.
		value, _ := new(big.Int).SetString(string(n), 10)
		return value.String(), nil
	}
	f, err := parseFloat(n)
	if err != nil {
		return "", err
	}
	return pythonFloat(f), nil
}

// isInteger reports whether Python reads the JSON number n as an int.
func isInteger(n json.Number) bool {
	return !strings.ContainsAny(string(n), ".eE")
}

// parseFloat returns the float64 of a JSON number, or an error when the number
// is outside the finite range.
func parseFloat(n json.Number) (float64, error) {
	f, err := strconv.ParseFloat(string(n), 64)
	if err != nil {
		return 0, fmt.Errorf("%w: %w", ErrInput, err)
	}
	return f, nil
}

// pythonFloat formats f as Python's repr(float) does: the shortest digits that
// read back as f, in fixed notation for decimal exponents from -4 to 15 and in
// scientific notation otherwise.
func pythonFloat(f float64) string {
	if f == 0 {
		if math.Signbit(f) {
			return "-0.0"
		}
		return "0.0"
	}
	mantissa, exponentText, _ := strings.Cut(strconv.FormatFloat(math.Abs(f), 'e', -1, 64), "e")
	exponent, _ := strconv.Atoi(exponentText)
	digits := strings.Replace(mantissa, ".", "", 1)
	sign := ""
	if f < 0 {
		sign = "-"
	}
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
