package source

import (
	"math"
	"math/big"
	"strconv"
	"strings"
)

func digits(text string) bool {
	if text == "" {
		return false
	}
	for _, c := range text {
		if c < '0' || c > '9' {
			return false
		}
	}
	return true
}
func signedDigits(text string) bool {
	if strings.HasPrefix(text, "+") || strings.HasPrefix(text, "-") {
		text = text[1:]
	}
	return digits(text)
}
func coreInteger(text string) bool {
	if signedDigits(text) {
		return true
	}
	if strings.HasPrefix(text, "0o") {
		return len(text) > 2 && strings.Trim(text[2:], "01234567") == ""
	}
	if strings.HasPrefix(text, "0x") {
		return len(text) > 2 && strings.Trim(text[2:], "0123456789abcdefABCDEF") == ""
	}
	return false
}
func coreFloat(text string) bool {
	unsigned := text
	if strings.HasPrefix(unsigned, "+") || strings.HasPrefix(unsigned, "-") {
		unsigned = unsigned[1:]
	}
	parts := strings.FieldsFunc(unsigned, func(r rune) bool { return r == 'e' || r == 'E' })
	hasExponent := strings.ContainsAny(unsigned, "eE")
	if hasExponent {
		if len(parts) != 2 || !signedDigits(parts[1]) || strings.Count(unsigned, "e")+strings.Count(unsigned, "E") != 1 {
			return false
		}
		unsigned = parts[0]
	}
	whole, fraction, dot := strings.Cut(unsigned, ".")
	if !dot {
		return hasExponent && digits(whole)
	}
	if whole == "" {
		return digits(fraction)
	}
	return digits(whole) && (fraction == "" || digits(fraction))
}
func resolve(text string, quoted bool, span Range, options Options) (any, error) {
	if quoted {
		return text, nil
	}
	switch text {
	case "", "~", nullText, "Null", "NULL":
		return nil, nil //nolint:nilnil // YAML null is an admitted JSON-domain value, not an invalid result.
	case trueText, "True", "TRUE":
		return true, nil
	case falseText, "False", "FALSE":
		return false, nil
	case ".inf", ".Inf", ".INF", "+.inf", "+.Inf", "+.INF":
		return math.Inf(1), nil
	case "-.inf", "-.Inf", "-.INF":
		return math.Inf(-1), nil
	case ".nan", ".NaN", ".NAN":
		return math.NaN(), nil
	}
	if coreInteger(text) {
		return integer(text, span, options)
	}
	if coreFloat(text) {
		f, err := strconv.ParseFloat(text, 64)
		if err != nil && !math.IsInf(f, 0) {
			return nil, failure("sdl.parse", Range{span.Start, span.Start}, options)
		}
		return f, nil
	}
	return text, nil
}
func integer(text string, span Range, options Options) (any, error) {
	unsigned := strings.TrimLeft(text, "+-")
	radix := 10
	if strings.HasPrefix(unsigned, "0o") {
		radix = 8
		unsigned = unsigned[2:]
	}
	if strings.HasPrefix(unsigned, "0x") {
		radix = 16
		unsigned = unsigned[2:]
	}
	magnitude := unsigned
	if radix != 10 {
		magnitude = strings.TrimLeft(magnitude, "0")
	}
	// Bound conversion work before allocating a big integer. The exact decimal
	// check below covers the few near-boundary hexadecimal/octal values.
	ceiling := 4300
	if radix == 8 {
		ceiling = 4762
	}
	if radix == 16 {
		ceiling = 3572
	}
	if len(magnitude) > ceiling {
		return nil, failure("sdl.parse", Range{span.Start, span.Start}, options)
	}
	i, ok := new(big.Int).SetString(unsigned, radix)
	if !ok {
		return nil, failure("sdl.parse", Range{span.Start, span.Start}, options)
	}
	if strings.HasPrefix(text, "-") {
		i.Neg(i)
	}
	rendered := i.String()
	if len(strings.TrimPrefix(rendered, "-")) > 4300 {
		return nil, failure("sdl.parse", Range{span.Start, span.Start}, options)
	}
	return number(rendered), nil
}
