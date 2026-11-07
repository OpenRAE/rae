package governance

import (
	"bytes"

	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/parser"
	"github.com/yuin/goldmark/text"
	"github.com/yuin/goldmark/util"
)

// MyST's colon fence has the same container and indentation behavior as a
// CommonMark code fence. Goldmark owns the surrounding block structure.
type colonFenceParser struct{}
type colonFence struct{ length, indent int }

func (colonFenceParser) Trigger() []byte             { return []byte{':'} }
func (colonFenceParser) CanInterruptParagraph() bool { return true }
func (colonFenceParser) CanAcceptIndentedLine() bool { return false }
func (colonFenceParser) Close(ast.Node, text.Reader, parser.Context) {
	// Goldmark owns the completed node; this parser has no state to release.
}

//nolint:ireturn // Implements Goldmark's block parser interface.
func (colonFenceParser) Open(_ ast.Node, reader text.Reader, pc parser.Context) (ast.Node, parser.State) {
	line, segment := reader.PeekLine()
	pos := pc.BlockOffset()
	if pos < 0 || pos >= len(line) || line[pos] != ':' {
		return nil, parser.NoChildren
	}
	end := pos
	for end < len(line) && line[end] == ':' {
		end++
	}
	if end-pos < 3 {
		return nil, parser.NoChildren
	}
	start := end + util.TrimLeftSpaceLength(line[end:])
	stop := len(line) - util.TrimRightSpaceLength(line)
	var info *ast.Text
	if start < stop {
		info = ast.NewTextSegment(text.NewSegment(segment.Start-segment.Padding+start, segment.Start-segment.Padding+stop))
	}
	node := ast.NewFencedCodeBlock(info)
	node.SetAttributeString("colon-fence", colonFence{end - pos, pos})
	return node, parser.NoChildren
}
func (colonFenceParser) Continue(node ast.Node, reader text.Reader, _ parser.Context) parser.State {
	line, segment := reader.PeekLine()
	raw, _ := node.AttributeString("colon-fence")
	fence, ok := raw.(colonFence)
	if !ok {
		return parser.Close
	}
	width, pos := util.IndentWidth(line, reader.LineOffset())
	if width < 4 && colonFenceEnd(line[pos:], fence.length) {
		reader.AdvanceToEOL()
		return parser.Close
	}
	pos, padding := util.IndentPositionPadding(line, reader.LineOffset(), segment.Padding, fence.indent)
	if pos < 0 {
		pos = max(0, util.FirstNonSpacePosition(line)) - segment.Padding
		padding = 0
	}
	body := text.NewSegmentPadding(segment.Start+pos, segment.Stop, padding)
	body.ForceNewline = true
	node.Lines().Append(body)
	reader.AdvanceToEOL()
	return parser.Continue | parser.NoChildren
}
func colonFenceEnd(line []byte, length int) bool {
	end := len(line) - len(bytes.TrimLeft(line, ":"))
	return end >= length && util.IsBlank(line[end:])
}
