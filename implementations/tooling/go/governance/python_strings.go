package governance

import (
	"strconv"
	"strings"
	"unicode/utf8"

	ts "github.com/odvcencio/gotreesitter"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

type pythonStringChunk struct {
	text       string
	raw, bytes bool
}

func pythonLiteralNames(root *ts.Node, source []byte, lang *ts.Language) (admission.PythonPatternSyntax, bool) {
	chunks, valid := pythonStringChunks(root, source, lang)
	if !valid {
		return admission.PythonPatternSyntax{}, false
	}
	named, valid := pythonResolveNames(chunks)
	if !valid {
		return named, false
	}
	for _, chunk := range chunks {
		if !chunk.raw {
			if _, valid := pythonStringContentMode(chunk.text, chunk.bytes, named); !valid {
				return named, false
			}
		}
	}
	return named, true
}

func pythonStringChunks(root *ts.Node, source []byte, lang *ts.Language) ([]pythonStringChunk, bool) {
	chunks := []pythonStringChunk{}
	pending := []*ts.Node{root}
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		switch node.Type(lang) {
		case "print_statement", "exec_statement":
			return nil, false
		case "concatenated_string":
			if !pythonStringFamiliesMatch(node, source, lang) {
				return nil, false
			}
		case pythonStringNode:
			parts, valid := pythonNodeStringChunks(node, source, lang)
			if !valid {
				return nil, false
			}
			chunks = append(chunks, parts...)
		}
		for i := range node.NamedChildCount() {
			pending = append(pending, node.NamedChild(i))
		}
	}
	return chunks, true
}

func pythonStringFamiliesMatch(node *ts.Node, source []byte, lang *ts.Language) bool {
	family := ""
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		if child.Type(lang) == pythonComment {
			continue
		}
		token := child.Text(source)
		start := strings.IndexAny(token, "\"'")
		if start < 0 {
			return false
		}
		prefix := strings.ToLower(token[:start])
		current := "text"
		if strings.Contains(prefix, "b") {
			current = "bytes"
		} else if strings.Contains(prefix, "t") {
			current = "template"
		}
		if family != "" && family != current {
			return false
		}
		family = current
	}
	return true
}

func pythonNodeStringChunks(node *ts.Node, source []byte, lang *ts.Language) ([]pythonStringChunk, bool) {
	token := node.Text(source)
	start := strings.IndexAny(token, "\"'")
	if start < 0 {
		return nil, false
	}
	prefix := strings.ToLower(token[:start])
	chunks := []pythonStringChunk{}
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		if child.Type(lang) != "string_content" {
			continue
		}
		text := child.Text(source)
		bytesLiteral := strings.Contains(prefix, "b")
		if bytesLiteral && strings.IndexFunc(text, func(r rune) bool { return r > 127 }) >= 0 {
			return nil, false
		}
		chunks = append(chunks, pythonStringChunk{text: text, bytes: bytesLiteral, raw: strings.Contains(prefix, "r")})
	}
	return chunks, true
}

func pythonResolveNames(chunks []pythonStringChunk) (admission.PythonPatternSyntax, bool) {
	var probe strings.Builder
	for _, chunk := range chunks {
		if chunk.raw || chunk.bytes {
			continue
		}
		names, valid := pythonNamedEscapes(chunk.text)
		if !valid {
			return admission.PythonPatternSyntax{}, false
		}
		probe.WriteString(names)
	}
	if probe.Len() == 0 {
		return admission.PythonPatternSyntax{}, true
	}
	named, err := admission.ParsePythonPattern(probe.String())
	return named, err == nil
}

func pythonStringContentMode(source string, bytesLiteral bool, syntax admission.PythonPatternSyntax) (string, bool) {
	var out strings.Builder
	for i := 0; i < len(source); {
		if source[i] != '\\' {
			out.WriteByte(source[i])
			i++
			continue
		}
		part, next, valid := pythonStringEscape(source, i, syntax, bytesLiteral)
		if !valid {
			return "", false
		}
		out.WriteString(part)
		i = next
	}
	return out.String(), true
}

func pythonStringEscape(source string, index int, syntax admission.PythonPatternSyntax, bytesLiteral bool) (string, int, bool) {
	if index+1 >= len(source) {
		return "", 0, false
	}
	code := source[index+1]
	switch {
	case code == '\n':
		return "", index + 2, true
	case strings.ContainsRune("\\\"'", rune(code)):
		return string(code), index + 2, true
	case code == 'N' && !bytesLiteral:
		name, _, _ := strings.Cut(source[index+3:], "}")
		value, ok := syntax.NamedCharacter(name)
		return string(value), index + len(name) + 4, ok
	case code == 'x' || !bytesLiteral && (code == 'u' || code == 'U'):
		return pythonHexEscape(source, index, code)
	case code >= '0' && code <= '7':
		end := index + 1
		for end < min(len(source), index+4) && source[end] >= '0' && source[end] <= '7' {
			end++
		}
		value, err := strconv.ParseUint(source[index+1:end], 8, 9)
		return string(rune(value)), end, err == nil
	case strings.ContainsRune("abfnrtv", rune(code)):
		value, _, rest, err := strconv.UnquoteChar(source[index:], 0)
		return string(value), len(source) - len(rest), err == nil
	default:
		return source[index : index+2], index + 2, true
	}
}

func pythonHexEscape(source string, index int, code byte) (string, int, bool) {
	width := 2
	switch code {
	case 'u':
		width = 4
	case 'U':
		width = 8
	}
	end := index + 2 + width
	if end > len(source) {
		return "", 0, false
	}
	raw := source[index+2 : end]
	if strings.IndexFunc(raw, func(r rune) bool { return !strings.ContainsRune("0123456789abcdefABCDEF", r) }) >= 0 {
		return "", 0, false
	}
	value, err := strconv.ParseUint(raw, 16, 32)
	if err != nil || value > utf8.MaxRune {
		return "", 0, false
	}
	if value >= 0xd800 && value <= 0xdfff {
		return string([]byte{0xe0 | byte(value>>12), 0x80 | byte(value>>6&0x3f), 0x80 | byte(value&0x3f)}), end, true
	}
	return string(rune(value)), end, true
}

func pythonNamedEscapes(source string) (string, bool) {
	var names strings.Builder
	for i := 0; i < len(source); i++ {
		if source[i] != '\\' || i+1 >= len(source) {
			continue
		}
		if source[i+1] == 'N' {
			end := strings.IndexByte(source[i+2:], '}')
			if i+2 >= len(source) || source[i+2] != '{' || end < 0 {
				return "", false
			}
			end += i + 3
			names.WriteString(source[i:end])
			i = end - 1
		} else {
			i++
		}
	}
	return names.String(), true
}
