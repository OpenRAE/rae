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
// member replaces an earlier one, as in Python. Sorted with ascii preserves
// lone UTF-16 surrogate escapes for legacy digest compatibility. JCS and the
// Unicode Sorted form refuse surviving lone surrogates.
package canonjson

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"maps"
	"math"
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

// decode returns one JSON value, retaining number text and surrogate identity.
func decode(data []byte) (any, error) {
	// Validate the entire document first: Decoder.Token alone does not enforce
	// the standard library's nesting limit across separate token calls.
	if !utf8.Valid(data) || !json.Valid(data) {
		return nil, fmt.Errorf("%w: invalid UTF-8 or JSON", ErrInput)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	return decodeValue(decoder, data)
}

// decodeValue walks syntax already validated by encoding/json. Each string's
// original spelling is available through InputOffset, before Go replaces a
// lone surrogate with U+FFFD. All decoded strings use the same private format.
func decodeValue(decoder *json.Decoder, data []byte) (any, error) {
	start := decoder.InputOffset()
	token, _ := decoder.Token() // Syntax and depth were validated in decode.
	switch v := token.(type) {
	case string:
		raw := data[start:decoder.InputOffset()]
		return decodeString(raw[bytes.IndexByte(raw, '"'):]), nil
	case json.Number:
		if isInteger(v) && len(strings.TrimPrefix(string(v), "-")) > maxDigits {
			return nil, fmt.Errorf("%w: an integer has more than %d digits", ErrInput, maxDigits)
		}
	case json.Delim:
		if v == '[' {
			return decodeArray(decoder, data)
		}
		return decodeObject(decoder, data)
	}
	return token, nil
}

// decodeArray reads the contents and closing delimiter of a validated array.
func decodeArray(decoder *json.Decoder, data []byte) ([]any, error) {
	values := []any{}
	for decoder.More() {
		item, err := decodeValue(decoder, data)
		if err != nil {
			return nil, err
		}
		values = append(values, item)
	}
	_, _ = decoder.Token()
	return values, nil
}

// decodeObject applies Python's last-member-wins rule to validated members.
func decodeObject(decoder *json.Decoder, data []byte) (map[string]any, error) {
	members := map[string]any{}
	for decoder.More() {
		start := decoder.InputOffset()
		_, _ = decoder.Token() // Object keys are strings in validated JSON.
		raw := data[start:decoder.InputOffset()]
		key := decodeString(raw[bytes.IndexByte(raw, '"'):])
		value, err := decodeValue(decoder, data)
		if err != nil {
			return nil, err
		}
		members[key] = value
	}
	_, _ = decoder.Token()
	return members, nil
}

// decodeString decodes a validated JSON string. A lone surrogate is retained
// as its three-byte code-point encoding, private to this encoder. This sorts
// in code-point order like UTF-8 and cannot collide with valid Unicode.
func decodeString(raw []byte) string {
	var out strings.Builder
	for i := 1; i < len(raw)-1; i++ {
		if raw[i] != '\\' {
			out.WriteByte(raw[i])
			continue
		}
		i++
		if raw[i] != 'u' {
			escape := map[byte]byte{'"': '"', '\\': '\\', '/': '/', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
			out.WriteByte(escape[raw[i]])
			continue
		}
		r, end := decodeUnit(raw, i)
		i = end
		if utf16.IsSurrogate(r) {
			out.WriteByte(0xe0 | byte((r>>12)&0x0f))
			out.WriteByte(0x80 | byte((r>>6)&0x3f))
			out.WriteByte(0x80 | byte(r&0x3f))
		} else {
			out.WriteRune(r)
		}
	}
	return out.String()
}

// decodeUnit decodes a validated Unicode escape and, when present, its pair.
// end is the index of the last consumed hexadecimal digit.
func decodeUnit(raw []byte, start int) (r rune, end int) {
	unit, _ := strconv.ParseUint(string(raw[start+1:start+5]), 16, 16)
	r = rune(unit)
	end = start + 4
	if r < 0xd800 || r > 0xdbff || end+6 >= len(raw) || raw[end+1] != '\\' || raw[end+2] != 'u' {
		return r, end
	}
	low, _ := strconv.ParseUint(string(raw[end+3:end+7]), 16, 16)
	if pair := utf16.DecodeRune(r, rune(low)); pair != utf8.RuneError {
		return pair, end + 6
	}
	return r, end
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
		return e.quote(v)
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
		if err := e.quote(key); err != nil {
			return err
		}
		e.out.WriteByte(':')
		if err := e.value(members[key]); err != nil {
			return err
		}
	}
	e.out.WriteByte('}')
	return nil
}

// quote writes s as a JSON string with the escapes of Python's json module.
func (e *encoder) quote(s string) error {
	e.out.WriteByte('"')
	for len(s) > 0 {
		r, size := utf8.DecodeRuneInString(s)
		if r == utf8.RuneError && size == 1 {
			// Only decodeString can produce invalid UTF-8 here, and only for
			// one retained surrogate. No replacement is permitted.
			if !e.ascii {
				return fmt.Errorf("%w: a string contains a lone surrogate", ErrInput)
			}
			r = rune(s[0]&0x0f)<<12 | rune(s[1]&0x3f)<<6 | rune(s[2]&0x3f)
			size = 3
		}
		s = s[size:]
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
	return nil
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
