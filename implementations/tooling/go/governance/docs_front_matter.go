package governance

import (
	"bytes"

	"github.com/yuin/goldmark/util"
)

func withoutDocumentMetadata(source []byte) []byte {
	if !bytes.HasPrefix(source, []byte("---")) {
		return source
	}
	first := bytes.IndexByte(source, '\n')
	if first < 0 {
		return source
	}
	length := len(source) - len(bytes.TrimLeft(source, "-"))
	previous := []byte{}
	for start := first + 1; start < len(source); {
		line, _, found := bytes.Cut(source[start:], []byte{'\n'})
		next := start + len(line)
		if found {
			next++
		}
		if bytes.Equal(previous, []byte("...")) {
			return source[start:]
		}
		width, pos := util.IndentWidth(line, 0)
		if width < 4 && metadataFenceEnd(line[pos:], length) {
			return source[next:]
		}
		previous = bytes.TrimLeft(line, " \t")
		start = next
	}
	return source
}
func metadataFenceEnd(line []byte, length int) bool {
	count := len(line) - len(bytes.TrimLeft(line, "-"))
	return count >= length && util.IsBlank(line[count:])
}
