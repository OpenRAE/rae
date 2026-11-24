package admission

import (
	"strconv"
	"strings"
)

const (
	patternASCII uint8 = 1 << iota
	patternUnicodeFlag
	patternVerbose
	patternIgnoreCase
	patternMultiline
	patternDotAll
)

func (p *pythonPattern) group() (patternWidth, bool, bool) {
	if !p.consume('?') {
		return p.groupBody(p.openGroup(""), 0), true, true
	}
	switch p.peek() {
	case 'P':
		return p.namedGroup(), true, true
	case '(':
		p.pos++
		return p.conditional(), true, true
	case ':', '>':
		p.pos++
		return p.groupBody(-1, 0), true, true
	case '=', '!':
		p.pos++
		return p.groupBody(-1, 1), true, true
	case '<':
		p.pos++
		if p.peek() != '=' && p.peek() != '!' {
			p.bad = true
			return patternWidth{}, false, false
		}
		p.pos++
		return p.groupBody(-1, -1), true, true
	default:
		return p.flagGroup()
	}
}

func (p *pythonPattern) openGroup(name string) int {
	id := len(p.groups)
	p.groups = append(p.groups, patternWidth{})
	p.closed = append(p.closed, false)
	if name != "" {
		if !p.identifier(name) || p.names[name] != 0 {
			p.bad = true
		}
		p.names[name] = id
	}
	return id
}

func (p *pythonPattern) groupBody(id, direction int) patternWidth {
	previousFlags, previousLookbehind := p.flags, p.lookbehind
	if direction < 0 && p.lookbehind < 0 {
		p.lookbehind = len(p.groups)
	}
	width := p.expression(0)
	p.flags, p.lookbehind = previousFlags, previousLookbehind
	if !p.consume(')') {
		p.bad = true
	}
	if id > 0 {
		p.groups[id], p.closed[id] = width, true
	}
	if direction < 0 && (width.low != width.high || width.low >= 1<<32) {
		p.bad = true
	}
	if direction != 0 {
		return patternWidth{}
	}
	return width
}

func (p *pythonPattern) until(end rune) string {
	start := p.pos
	for p.pos < len(p.text) && p.peek() != end {
		p.pos++
	}
	result := string(p.text[start:p.pos])
	if !p.consume(end) {
		p.bad = true
	}
	return result
}

func (p *pythonPattern) namedGroup() patternWidth {
	p.pos++ // P
	if p.consume('<') {
		name := p.until('>')
		if !p.identifier(name) {
			p.bad = true
		}
		return p.groupBody(p.openGroup(name), 0)
	}
	if !p.consume('=') {
		p.bad = true
		return patternWidth{}
	}
	name := p.until(')')
	if !p.identifier(name) {
		p.bad = true
	}
	return p.reference(p.names[name])
}

func (p *pythonPattern) conditional() patternWidth {
	name := p.until(')')
	id := p.names[name]
	if patternDigits(name) {
		parsed, err := strconv.ParseUint(name, 10, 31)
		if err != nil || parsed == 0 {
			p.bad = true
		}
		id = int(parsed)
		p.conditions = append(p.conditions, id)
	} else if !p.identifier(name) || id == 0 {
		p.bad = true
	}
	if p.lookbehind >= 0 && (id >= len(p.closed) || !p.closed[id] || id >= p.lookbehind) {
		p.bad = true
	}
	previous := p.flags
	width := p.expression(2)
	p.flags = previous
	if !p.consume(')') {
		p.bad = true
	}
	// Without an else branch Python's conditional can also match the empty
	// sequence. This matters when the expression is inside a lookbehind.
	return width
}

func patternFlag(c rune) uint8 {
	switch c {
	case 'a':
		return patternASCII
	case 'u':
		return patternUnicodeFlag
	case 'x':
		return patternVerbose
	case 'i':
		return patternIgnoreCase
	case 'm':
		return patternMultiline
	case 's':
		return patternDotAll
	default:
		return 0
	}
}

func (p *pythonPattern) flagGroup() (patternWidth, bool, bool) {
	var add, remove uint8
	for patternFlag(p.peek()) != 0 {
		add |= patternFlag(p.peek())
		p.pos++
	}
	hasRemove := p.consume('-')
	if hasRemove {
		for patternFlag(p.peek()) != 0 {
			remove |= patternFlag(p.peek())
			p.pos++
		}
	}
	if invalidPatternFlags(add, remove, hasRemove) {
		p.bad = true
	}
	if !hasRemove && p.consume(')') {
		if !p.start || p.depth != 1 {
			p.bad = true
		}
		p.flags |= add
		return patternWidth{}, false, false
	}
	if !p.consume(':') {
		p.bad = true
		return patternWidth{}, false, false
	}
	previous := p.flags
	if add&(patternASCII|patternUnicodeFlag) != 0 {
		p.flags &^= patternASCII | patternUnicodeFlag
	}
	p.flags = (p.flags | add) &^ remove
	width := p.groupBody(-1, 0)
	p.flags = previous
	return width, true, true
}

func patternDigits(s string) bool {
	return s != "" && strings.IndexFunc(s, func(c rune) bool { return c < '0' || c > '9' }) < 0
}

func invalidPatternFlags(add, remove uint8, hasRemove bool) bool {
	return add == 0 && remove == 0 || hasRemove && remove == 0 || remove&(patternASCII|patternUnicodeFlag) != 0 || add&remove != 0 || add&(patternASCII|patternUnicodeFlag) == patternASCII|patternUnicodeFlag
}
