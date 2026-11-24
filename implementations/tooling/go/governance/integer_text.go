package governance

import (
	"strings"
	"unicode"
	"unicode/utf8"
)

func pythonIntegerText(text string) (string, bool) {
	text = strings.TrimFunc(text, pythonIntegerSpace)
	sign := ""
	if strings.HasPrefix(text, "+") || strings.HasPrefix(text, "-") {
		sign = text[:1]
		text = text[1:]
	}
	var out strings.Builder
	digitBefore := false
	for _, r := range text {
		if r == '_' {
			if !digitBefore {
				return "", false
			}
			digitBefore = false
			continue
		}
		digit, ok := unicodeDecimal(r)
		if !ok {
			return "", false
		}
		out.WriteByte('0' + digit)
		digitBefore = true
	}
	if !digitBefore || out.Len() > 4300 {
		return "", false
	}
	digits := strings.TrimLeft(out.String(), "0")
	if digits == "" {
		return "0", true
	}
	if sign == "-" {
		return sign + digits, true
	}
	return digits, true
}

func unicodeDecimal(r rune) (byte, bool) {
	if r < 0 || r > utf8.MaxRune || !unicode.Is(pythonAssigned(), r) {
		return 0, false
	}
	code := uint32(r)
	for _, span := range unicode.Nd.R16 {
		if code >= uint32(span.Lo) && code <= uint32(span.Hi) && (code-uint32(span.Lo))%uint32(span.Stride) == 0 {
			return byte((code - uint32(span.Lo)) / uint32(span.Stride) % 10), true
		}
	}
	for _, span := range unicode.Nd.R32 {
		if code >= span.Lo && code <= span.Hi && (code-span.Lo)%span.Stride == 0 {
			return byte((code - span.Lo) / span.Stride % 10), true
		}
	}
	return 0, false
}

func pythonIntegerSpace(r rune) bool { return pythonWhitespace(r) && (r < 0x1c || r > 0x1f) }
