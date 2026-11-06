package governance

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"sync/atomic"
	"unicode/utf8"

	ts "github.com/odvcencio/gotreesitter"
	"github.com/odvcencio/gotreesitter/grammars"
	"github.com/santhosh-tekuri/jsonschema/v6"
	"github.com/yuin/goldmark"
	"github.com/yuin/goldmark/ast"
	"github.com/yuin/goldmark/parser"
	"github.com/yuin/goldmark/text"
	"go.yaml.in/yaml/v3"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
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

// decodeJSON selects the owning surface's duplicate policy and byte limit.
// A zero byte limit means the reference has no explicit ceiling. The strict
// object profile reuses the existing published ingress owner.
func decodeJSON(data []byte, limit int, unique bool) (any, error) {
	if limit > 0 && len(data) > limit {
		return nil, errors.New("JSON source exceeds its byte limit")
	}
	if unique {
		return ingress.Parse(data, ingress.Limits{MaxBytes: max(1, len(data)), MaxDepth: 0}, ingress.Object)
	}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return nil, errors.New("multiple JSON values")
	}
	return value, nil
}

// markdownSyntax retains reference definitions, including unused definitions.
// It parses text only; directives are never rendered or executed here.
func markdownSyntax(source []byte) (ast.Node, parser.Context) {
	pc := parser.NewContext()
	return goldmark.New().Parser().Parse(text.NewReader(source), parser.WithContext(pc)), pc
}

type offlineSchemas struct{}

func (offlineSchemas) Load(string) (any, error) {
	return nil, errors.New("external schema retrieval forbidden")
}

// candidateSchema compiles supplied repository bytes, not the embedded base
// corpus. The semantic model checks separately reuse contract/admission.
func candidateSchema(data []byte) (*jsonschema.Schema, error) {
	var value any
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	compiler := jsonschema.NewCompiler()
	compiler.DefaultDraft(jsonschema.Draft2020)
	compiler.UseLoader(offlineSchemas{})
	const id = "https://governance.invalid/candidate"
	if err := compiler.AddResource(id, value); err != nil {
		return nil, err
	}
	return compiler.Compile(id)
}
