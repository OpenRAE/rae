package governance

import (
	"bytes"
	"slices"
	"strings"

	ts "github.com/odvcencio/gotreesitter"
)

// The packaged grammar admits several lexical forms that ast.parse refuses.
// Keep these input checks at the static-policy boundary, without executing a
// Python compiler or interpreting expressions.
func (p repoPythonReader) validSource(root *ts.Node) bool {
	masked := bytes.Clone(p.data)
	pending := []*ts.Node{root}
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		kind := node.Type(p.lang)
		if kind == "integer" && !repoPythonInteger(node.Text(p.data)) {
			return false
		}
		if kind == pythonStringNode || kind == pythonComment {
			repoMaskPython(masked, node.StartByte(), node.EndByte())
			continue
		}
		for i := range node.NamedChildCount() {
			pending = append(pending, node.NamedChild(i))
		}
	}
	return repoPythonMargins(masked)
}
func repoPythonInteger(value string) bool {
	digits := strings.ReplaceAll(value, "_", "")
	lower := strings.ToLower(digits)
	if strings.HasPrefix(lower, "0x") || strings.HasPrefix(lower, "0b") || strings.HasPrefix(lower, "0o") {
		return true
	}
	return len(digits) <= 4300 && (len(digits) <= 1 || digits[0] != '0' || strings.Trim(digits, "0") == "")
}
func repoMaskPython(masked []byte, start, end uint32) {
	for i := start; i < end; i++ {
		if masked[i] != '\n' && masked[i] != '\r' {
			masked[i] = ' '
		}
	}
}

func repoPythonMargins(source []byte) bool {
	state := repoPythonMarginState{columns: []int{0}, alternates: []int{0}}
	for line := range bytes.SplitSeq(source, []byte{'\n'}) {
		offset, column, alternate := repoPythonIndent(line)
		if offset == len(line) {
			continue
		}
		if len(state.brackets) == 0 && !state.continued && !state.indent(column, alternate) {
			return false
		}
		if !state.delimiters(line[offset:]) {
			return false
		}
		state.continued = len(line) > 0 && line[len(line)-1] == '\\'
	}
	return len(state.brackets) == 0
}

type repoPythonMarginState struct {
	brackets            []byte
	columns, alternates []int
	continued           bool
}

func repoPythonIndent(line []byte) (int, int, int) {
	column, alternate := 0, 0
	for offset, char := range line {
		switch char {
		case ' ':
			column++
			alternate++
		case '\t':
			column = (column/8 + 1) * 8
			alternate++
		case '\f':
			column = 0
			alternate = 0
		default:
			return offset, column, alternate
		}
	}
	return len(line), column, alternate
}
func (s *repoPythonMarginState) indent(column, alternate int) bool {
	last := len(s.columns) - 1
	if column > s.columns[last] {
		if alternate <= s.alternates[last] || len(s.columns) >= 100 {
			return false
		}
		s.columns = append(s.columns, column)
		s.alternates = append(s.alternates, alternate)
		return true
	}
	at := slices.Index(s.columns, column)
	if at < 0 || alternate != s.alternates[at] {
		return false
	}
	s.columns = s.columns[:at+1]
	s.alternates = s.alternates[:at+1]
	return true
}
func (s *repoPythonMarginState) delimiters(line []byte) bool {
	for _, char := range line {
		switch char {
		case '(', '[', '{':
			s.brackets = append(s.brackets, char)
			if len(s.brackets) > 200 {
				return false
			}
		case ')', ']', '}':
			if len(s.brackets) == 0 {
				return false
			}
			open := s.brackets[len(s.brackets)-1]
			s.brackets = s.brackets[:len(s.brackets)-1]
			if !repoPythonClosing(open, char) {
				return false
			}
		}
	}
	return true
}
func repoPythonClosing(open, closing byte) bool {
	return open == '(' && closing == ')' || open == '[' && closing == ']' || open == '{' && closing == '}'
}
