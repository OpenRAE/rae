package governance

import (
	"regexp"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// This is a spelling adapter for the published subset, not a matching engine.
const pythonSchemaSpace = `\t\n\v\f\r\x1c-\x1f\x85\p{Z}`
const javascriptSchemaSpace = `\t\n\v\f\r\x{feff}\p{Zs}\x{2028}\x{2029}`

var schemaRepetition = regexp.MustCompile(`^\{[0-9]+(?:,[0-9]*)?\}`)

const errSchemaPattern = policyInputError("schema pattern is outside the supported standard-library profile")

type schemaPattern struct {
	*regexp.Regexp

	source string
}

func (p schemaPattern) String() string { return p.source }

type schemaPatternWriter struct {
	source                string
	python                bool
	class, first, negated bool
	out                   strings.Builder
}

func compileSchemaPattern(source string, python bool) (schemaPattern, error) {
	if python {
		if _, err := admission.ParsePythonPattern(source); err != nil {
			return schemaPattern{}, policyInputError("schema pattern has invalid syntax")
		}
	}
	writer := schemaPatternWriter{source: source, python: python}
	for i := 0; i < len(source); i++ {
		consumed, err := writer.token(i)
		if err != nil {
			return schemaPattern{}, err
		}
		i += consumed
	}
	compiled, err := regexp.Compile(writer.out.String())
	if err != nil {
		return schemaPattern{}, errSchemaPattern
	}
	return schemaPattern{compiled, source}, nil
}

func (w *schemaPatternWriter) token(i int) (int, error) {
	source := w.source[i:]
	char := source[0]
	if char == '\\' && len(source) > 1 {
		text, consumed, err := schemaPatternEscape(source[1:], w.class, w.python)
		w.out.WriteString(text)
		w.first = false
		return consumed, err
	}
	if w.class {
		w.classByte(char)
		return 0, nil
	}
	if strings.HasPrefix(source, `$(?![\s\S])`) {
		w.out.WriteString(`\z`)
		return len(`$(?![\s\S])`) - 1, nil
	}
	if strings.HasPrefix(source, "(?") && !strings.HasPrefix(source, "(?:") {
		return 0, errSchemaPattern
	}
	switch char {
	case '[':
		return w.openClass(source), nil
	case '{', '}', ']':
		if !w.python {
			return w.javascriptPunctuation(source)
		}
		w.out.WriteByte(char)
	case '$':
		return 0, w.endAnchor(source)
	case '.':
		if w.python {
			w.out.WriteByte(char)
		} else {
			w.out.WriteString(`[^\r\n\x{2028}\x{2029}]`)
		}
	default:
		w.out.WriteByte(char)
	}
	return 0, nil
}

func (w *schemaPatternWriter) openClass(source string) int {
	if !w.python {
		if strings.HasPrefix(source, "[]") {
			w.out.WriteString(`(?:\b\B)`)
			return 1
		}
		if strings.HasPrefix(source, "[^]") {
			w.out.WriteString(`(?s:.)`)
			return 2
		}
	}
	w.class, w.first, w.negated = true, true, false
	w.out.WriteByte('[')
	return 0
}

func (w *schemaPatternWriter) classByte(char byte) {
	switch {
	case char == '^' && w.first && !w.negated:
		w.out.WriteByte(char)
		w.negated = true
		return
	case char == '[':
		w.out.WriteString(`\[`)
	case char == ']' && w.first:
		w.out.WriteString(`\]`)
	case char == ']':
		w.out.WriteByte(char)
		w.class = false
	default:
		w.out.WriteByte(char)
	}
	w.first = false
}

func schemaPatternEscape(text string, inClass, python bool) (string, int, error) {
	space, digits, word := javascriptSchemaSpace, `0-9`, `A-Za-z0-9_`
	if python {
		space, digits, word = pythonSchemaSpace, pythonSchemaDigits(), pythonSchemaWord()
	}
	classes := map[byte]string{'d': digits, 's': space, 'w': word}
	content, found := classes[text[0]|0x20]
	if !found {
		return schemaLiteralEscape(text, inClass, python)
	}
	negated := text[0] < 'a'
	if inClass {
		if negated {
			return "", 0, errSchemaPattern
		}
		return content, 1, nil
	}
	if negated {
		return "[^" + content + "]", 1, nil
	}
	return "[" + content + "]", 1, nil
}

func (w *schemaPatternWriter) endAnchor(source string) error {
	if !w.python {
		w.out.WriteString(`\z`)
		return nil
	}
	if strings.Trim(source[1:], ")") != "" {
		return errSchemaPattern
	}
	w.out.WriteString(`(?:\n?\z)`)
	return nil
}

func (w *schemaPatternWriter) javascriptPunctuation(source string) (int, error) {
	if source[0] != '{' {
		return 0, errSchemaPattern
	}
	repetition := schemaRepetition.FindString(source)
	if repetition == "" {
		return 0, errSchemaPattern
	}
	w.out.WriteString(repetition)
	return len(repetition) - 1, nil
}
