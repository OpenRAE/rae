package governance

import (
	"errors"
	"fmt"
	"strings"
	"unicode/utf8"
)

func yamlFailureText(data []byte, err error) string {
	if _, syntax := errors.AsType[*yamlSyntaxError](err); !syntax {
		return "the YAML document cannot be constructed"
	}
	message := err.Error()
	if strings.Contains(message, "did not find expected node content") {
		return "while parsing a flow node\nexpected the node content, but found '<stream end>'\n" + yamlEndMark(string(data))
	}
	return message
}

func yamlEndMark(source string) string {
	lines := strings.Split(source, "\n")
	last := lines[len(lines)-1]
	column := utf8.RuneCountInString(last) + 1
	mark := fmt.Sprintf("  in \"<unicode string>\", line %d, column %d", len(lines), column)
	if last == "" {
		return mark
	}
	return mark + ":\n    " + last + "\n" + strings.Repeat(" ", column+3) + "^"
}
