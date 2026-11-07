package governance

import (
	"bytes"
	"strings"
	"unicode/utf8"

	"github.com/yuin/goldmark/ast"
	definition "github.com/yuin/goldmark/extension/ast"
	"github.com/yuin/goldmark/parser"
	"github.com/yuin/goldmark/text"
	"github.com/yuin/goldmark/util"
)

type fieldListParser struct{}
type fieldBodyParser struct{}
type fieldMarker struct {
	name    text.Segment
	content int
}

func (fieldListParser) Trigger() []byte                             { return []byte{':'} }
func (fieldListParser) CanInterruptParagraph() bool                 { return true }
func (fieldListParser) CanAcceptIndentedLine() bool                 { return false }
func (fieldListParser) Close(ast.Node, text.Reader, parser.Context) {}

//nolint:ireturn // Implements Goldmark's block parser interface.
func (fieldListParser) Open(parent ast.Node, reader text.Reader, pc parser.Context) (ast.Node, parser.State) {
	if _, field := parent.AttributeString("field-marker"); field {
		return nil, parser.NoChildren
	}
	line, segment := reader.PeekLine()
	pos := pc.BlockOffset()
	marker, ok := documentationFieldMarker(line, segment, pos)
	if !ok {
		return nil, parser.NoChildren
	}
	firstIndent := utf8.RuneCount(line[:marker.content])
	indent := fieldBodyIndent(reader.Source()[segment.Stop:], reader.LineOffset(), firstIndent)
	node := definition.NewDefinitionList(indent, nil)
	node.SetAttributeString("field-marker", marker)
	return node, parser.HasChildren
}

func documentationFieldMarker(line []byte, segment text.Segment, pos int) (fieldMarker, bool) {
	if pos < 0 || pos >= len(line) || line[pos] != ':' {
		return fieldMarker{}, false
	}
	length := bytes.IndexByte(line[pos+1:], ':')
	if length < 1 || strings.TrimFunc(string(line[pos+1:pos+1+length]), pythonWhitespace) == "" {
		return fieldMarker{}, false
	}
	end := pos + 1 + length
	content := end + 1
	for content < len(line) && (line[content] == ' ' || line[content] == '\t') {
		content++
	}
	return fieldMarker{text.NewSegment(segment.Start-segment.Padding+pos+1, segment.Start-segment.Padding+end), content}, true
}

func (fieldListParser) Continue(node ast.Node, reader text.Reader, _ parser.Context) parser.State {
	line, _ := reader.PeekLine()
	if util.IsBlank(line) {
		return parser.Continue | parser.HasChildren
	}
	list, ok := node.(*definition.DefinitionList)
	if !ok {
		return parser.Close
	}
	width, _ := util.IndentWidth(line, reader.LineOffset())
	if width < list.Offset {
		return parser.Close
	}
	pos, padding := util.IndentPosition(line, reader.LineOffset(), list.Offset)
	reader.AdvanceAndSetPadding(pos, padding)
	return parser.Continue | parser.HasChildren
}

func (fieldBodyParser) Trigger() []byte             { return []byte{':'} }
func (fieldBodyParser) CanInterruptParagraph() bool { return true }
func (fieldBodyParser) CanAcceptIndentedLine() bool { return false }
func (fieldBodyParser) Continue(ast.Node, text.Reader, parser.Context) parser.State {
	return parser.Continue | parser.HasChildren
}
func (fieldBodyParser) Close(ast.Node, text.Reader, parser.Context) {}

//nolint:ireturn // Implements Goldmark's block parser interface.
func (fieldBodyParser) Open(parent ast.Node, reader text.Reader, _ parser.Context) (ast.Node, parser.State) {
	raw, found := parent.AttributeString("field-marker")
	marker, ok := raw.(fieldMarker)
	if !found || !ok || parent.FirstChild() != nil {
		return nil, parser.NoChildren
	}
	term := definition.NewDefinitionTerm()
	term.Lines().Append(marker.name)
	parent.AppendChild(parent, term)
	reader.Advance(marker.content)
	return definition.NewDefinitionDescription(), parser.HasChildren
}

// MyST chooses the least positive continuation indent, bounded by the first
// line's body position. Only container prefixes are removed during lookahead;
// Goldmark still parses every field name and body in the document context.
func fieldBodyIndent(source []byte, parentColumns, firstIndent int) int {
	indent := firstIndent
	for raw := range bytes.SplitSeq(source, []byte{'\n'}) {
		line, ok := fieldContainerPrefix(raw, parentColumns)
		if !ok {
			break
		}
		if util.IsBlank(line) {
			continue
		}
		width, _ := util.IndentWidth(line, 0)
		if width == 0 {
			break
		}
		indent = min(indent, width)
	}
	return indent
}

func fieldContainerPrefix(line []byte, columns int) ([]byte, bool) {
	width, pos := 0, 0
	for width < columns && pos < len(line) {
		switch line[pos] {
		case ' ', '>':
			width++
		case '\t':
			width += util.TabWidth(width)
		default:
			return nil, false
		}
		pos++
	}
	return line[pos:], width >= columns || util.IsBlank(line[pos:])
}
