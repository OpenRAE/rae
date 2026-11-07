package governance

import (
	"bytes"
	"net/url"
	"regexp"
	"slices"
	"strings"

	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/parser"
	"github.com/yuin/goldmark/util"
	"golang.org/x/net/idna"
)

const directiveFence = "^[ \\t]*[`~:]{3,}[ \\t]*\\{"
const directiveFileOption = "[\"']?(?:file|url|diff)[\"']?[ \\t]*:[ \\t]+([^" + pythonSchemaSpace + "]+)"

var directiveArgument = regexp.MustCompile(`(?im)^[` + pythonSchemaSpace + `]*\.\.[` + pythonSchemaSpace + `]+(?:include|literalinclude|download)::[` + pythonSchemaSpace + `]+([^` + pythonSchemaSpace + `]+)`)
var mystDirectiveArgument = regexp.MustCompile(`(?im)` + directiveFence + `(?:include|literalinclude|download)\}[` + pythonSchemaSpace + `]+([^` + pythonSchemaSpace + `]+)`)
var downloadRole = regexp.MustCompile("(?i)\\{download\\}`(?:[^`<]*<)?([^>`]+)>?`")
var directiveOption = regexp.MustCompile(`(?im)^[ \t]*:` + directiveFileOption)
var directiveOpening = regexp.MustCompile(directiveFence)
var directiveYAMLOption = regexp.MustCompile(`(?i)^[ \t]*` + directiveFileOption)

func directiveTargets(source string) []string {
	targets := []string{}
	for _, pattern := range []*regexp.Regexp{directiveArgument, mystDirectiveArgument, downloadRole, directiveOption} {
		for _, match := range pattern.FindAllStringSubmatch(source, -1) {
			targets = append(targets, match[1])
		}
	}
	targets = append(targets, directiveYAMLTargets(source)...)
	for i, target := range targets {
		targets[i] = strings.Trim(strings.TrimFunc(target, pythonWhitespace), "\"'")
	}
	return targets
}

func directiveYAMLTargets(source string) []string {
	targets := []string{}
	lines := pythonLines(source, false)
	for i, line := range lines {
		if !directiveOpening.MatchString(line) || i+1 == len(lines) || !strings.HasPrefix(strings.TrimLeftFunc(lines[i+1], pythonWhitespace), "---") {
			continue
		}
		for _, option := range lines[i+2:] {
			if strings.HasPrefix(strings.TrimLeftFunc(option, pythonWhitespace), "---") {
				break
			}
			if match := directiveYAMLOption.FindStringSubmatch(option); match != nil {
				targets = append(targets, match[1])
			}
		}
	}
	return targets
}

func markdownLinkTargets(source string) []string {
	targets := []string{}
	pending := []string{source}
	for len(pending) > 0 {
		current := []byte(pending[len(pending)-1])
		pending = pending[:len(pending)-1]
		root, pc := markdownSyntax(current)
		targets = append(targets, markdownReferenceTargets(root, pc)...)
		inline, bodies := markdownInlineTargets(root, current)
		targets = append(targets, inline...)
		pending = append(pending, bodies...)
	}
	return uniqueStrings(targets)
}

func markdownReferenceTargets(root ast.Node, pc parser.Context) []string {
	targets := []string{}
	references := map[string]bool{}
	_ = ast.Walk(root, func(node ast.Node, entering bool) (ast.WalkStatus, error) {
		if ref, ok := node.(*ast.LinkReferenceDefinition); entering && ok {
			label := util.ToLinkReference(ref.Label)
			if !references[label] && !bytes.HasPrefix(ref.Label, []byte("^")) {
				references[label] = true
				if value, found := pc.Reference(label); found {
					targets = appendMarkdownTarget(targets, value.Destination())
				}
			}
		}
		return ast.WalkContinue, nil
	})
	return targets
}

func markdownInlineTargets(root ast.Node, current []byte) ([]string, []string) {
	targets, pending := []string{}, []string{}

	_ = ast.Walk(root, func(node ast.Node, entering bool) (ast.WalkStatus, error) {
		if !entering {
			return ast.WalkContinue, nil
		}
		switch node := node.(type) {
		case *ast.Link:
			targets = appendMarkdownTarget(targets, node.Destination)
		case *ast.Image:
			targets = appendMarkdownTarget(targets, node.Destination)
		case *ast.AutoLink:
			targets = appendMarkdownTarget(targets, node.URL(current))
		case *ast.FencedCodeBlock:
			info := ""
			if node.Info != nil {
				info = string(node.Info.Segment.Value(current))
			}
			if markdownDirectiveBody(info, node) {
				pending = append(pending, string(node.Lines().Value(current)))
			}
		}
		return ast.WalkContinue, nil
	})
	return targets, pending
}

func markdownDirectiveBody(info string, node ast.Node) bool {
	words := strings.FieldsFunc(info, pythonWhitespace)
	name := ""
	if len(words) > 0 {
		name = words[0]
	}
	if strings.HasPrefix(name, "{") && strings.HasSuffix(name, "}") {
		return !slices.Contains([]string{"code", "code-block", "sourcecode", "literalinclude", "raw", "math", "eval-rst", "csv-table"}, strings.ToLower(name[1:len(name)-1]))
	}
	_, colon := node.AttributeString("colon-fence")
	return colon
}

func appendMarkdownTarget(targets []string, destination []byte) []string {
	target := string(util.URLEscape(destination, true))
	scheme, _, hasScheme := strings.Cut(strings.ToLower(target), ":")
	if hasScheme && slices.Contains([]string{"file", "javascript", "vbscript", "data"}, scheme) {
		return targets
	}
	if parsed, err := url.Parse(target); err == nil && parsed.Host != "" {
		if host, err := idna.ToASCII(parsed.Hostname()); err == nil {
			parsed.Host = strings.Replace(parsed.Host, parsed.Hostname(), host, 1)
			target = parsed.String()
		}
	}
	return append(targets, target)
}

func uniqueStrings(values []string) []string {
	result := []string{}
	seen := map[string]bool{}
	for _, value := range values {
		if !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	return result
}
