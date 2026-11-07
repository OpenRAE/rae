package governance

import (
	"bytes"
	"context"
	"errors"
	"io"
	"sync/atomic"
	"unicode/utf8"

	ts "github.com/odvcencio/gotreesitter"
	"github.com/odvcencio/gotreesitter/grammars"
	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/extension"
	"github.com/yuin/goldmark/parser"
	"github.com/yuin/goldmark/text"
	"github.com/yuin/goldmark/util"
	"go.yaml.in/yaml/v3"
)

// yamlDocument returns syntax, leaving the reference's scalar, alias and
// duplicate-key policy to the owning surface. It accepts exactly one document.
func yamlDocument(data []byte) (*yaml.Node, error) {
	if !utf8.Valid(data) {
		return nil, errors.New("yaml source is not UTF-8")
	}
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	var node yaml.Node
	if err := decoder.Decode(&node); err != nil {
		if errors.Is(err, io.EOF) {
			return &yaml.Node{}, nil
		}
		return nil, err
	}
	var extra yaml.Node
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return nil, errors.New("expected a single YAML document")
	}
	return &node, nil
}

// pythonSyntax parses repository Python without executing it. Callers release
// the returned arena-backed tree after use.
func pythonSyntax(ctx context.Context, source []byte) (*ts.Tree, error) {
	if !utf8.Valid(source) || bytes.IndexByte(source, 0) >= 0 {
		return nil, errors.New("not valid Python source")
	}
	lang := grammars.PythonLanguage()
	p := ts.NewParser(lang)
	var cancelled uint32
	p.SetCancellationFlag(&cancelled)
	stop := context.AfterFunc(ctx, func() { atomic.StoreUint32(&cancelled, 1) })
	defer stop()
	tree, err := p.ParseStrict(source)
	if err != nil {
		if tree != nil {
			tree.Release()
		}
		return nil, err
	}
	if err := ctx.Err(); err != nil {
		tree.Release()
		return nil, err
	}
	if tree.RootNode().HasErrorOrMissing() {
		tree.Release()
		return nil, errors.New("not valid Python source")
	}

	return tree, nil
}

// markdownSyntax retains reference definitions, including unused definitions.
// It parses text only; directives are never rendered or executed here.
//
//nolint:ireturn // Goldmark owns the node and parser-context interfaces.
func markdownSyntax(source []byte) (ast.Node, parser.Context) {
	pc := parser.NewContext()
	markdown := goldmark.New(goldmark.WithExtensions(extension.DefinitionList, extension.TaskList), goldmark.WithParserOptions(parser.WithBlockParsers(util.Prioritized(fieldListParser{}, 99), util.Prioritized(fieldBodyParser{}, 100), util.Prioritized(colonFenceParser{}, 650))))
	// Keep source positions unchanged for consumers of AST text segments.
	source = maskDocumentMetadata(source)
	return markdown.Parser().Parse(text.NewReader(source), parser.WithContext(pc)), pc
}

func maskDocumentMetadata(source []byte) []byte {
	body := withoutDocumentMetadata(source)
	if len(body) == len(source) {
		return source
	}
	masked := bytes.Clone(source)
	for i := range len(source) - len(body) {
		if masked[i] != '\n' && masked[i] != '\r' {
			masked[i] = ' '
		}
	}
	return masked
}

type offlineSchemas struct{}

func (offlineSchemas) Load(string) (any, error) {
	return nil, errors.New("external schema retrieval forbidden")
}
