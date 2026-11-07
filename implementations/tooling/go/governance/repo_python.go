package governance

import (
	"context"
	"errors"
	"strings"

	ts "github.com/odvcencio/gotreesitter"
	"github.com/odvcencio/gotreesitter/grammars"
	"golang.org/x/text/unicode/norm"
)

const invalidPythonSource = " is not valid Python source"

type repoPythonImport struct {
	module         string
	names          []string
	from, relative bool
}
type repoPythonFacts struct {
	imports []repoPythonImport
	untyped []string
}

func repoReadText(r *repository, name string) (string, error) {
	text, err := r.text(name)
	if errors.Is(err, errNotUTF8) {
		return "", policyInputError(name + " is not UTF-8 text")
	}
	if err != nil {
		return "", repoPolicyError(name + " could not be read")
	}
	return text, nil
}

func repoPython(ctx context.Context, r *repository, name string) (repoPythonFacts, error) {
	source, err := repoReadText(r, name)
	if err != nil {
		return repoPythonFacts{}, err
	}
	data := []byte(source)
	tree, err := pythonSyntax(ctx, data)
	if err != nil {
		return repoPythonFacts{}, policyInputError(name + invalidPythonSource)
	}
	defer tree.Release()
	lang := grammars.PythonLanguage()
	root := tree.RootNode()
	if _, valid := pythonLiteralNames(root, data, lang); !valid {
		return repoPythonFacts{}, policyInputError(name + invalidPythonSource)
	}
	reader := repoPythonReader{data, lang}
	if !reader.validSource(root) {
		return repoPythonFacts{}, policyInputError(name + invalidPythonSource)
	}
	facts := repoPythonFacts{imports: []repoPythonImport{}, untyped: []string{}}
	// Transparent syntax containers do not add an AST level. The queue thus
	// retains ast.walk's breadth-first order, including exception handlers.
	pending := []*ts.Node{root}
	for len(pending) > 0 {
		next := []*ts.Node{}
		for _, node := range pending {
			kind := node.Type(lang)
			if kind == "import_statement" || kind == "import_from_statement" {
				facts.imports = append(facts.imports, reader.importNode(node))
			}
			reader.statements(node, &next)
		}
		pending = next
	}
	for i := range root.NamedChildCount() {
		node := reader.undecorate(root.NamedChild(i))
		if node.Type(lang) == "class_definition" {
			facts.untyped = append(facts.untyped, reader.protocol(node)...)
		}
	}
	return facts, nil
}

type repoPythonReader struct {
	data []byte
	lang *ts.Language
}

func (p repoPythonReader) statements(node *ts.Node, next *[]*ts.Node) {
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		kind := child.Type(p.lang)
		if strings.HasSuffix(kind, "_statement") || kind == "class_definition" || kind == "function_definition" || kind == "elif_clause" || kind == "except_clause" || kind == "case_clause" {
			*next = append(*next, child)
		} else {
			p.statements(child, next)
		}
	}
}
func (p repoPythonReader) identifier(node *ts.Node) string {
	if node == nil {
		return ""
	}
	return norm.NFKC.String(node.Text(p.data))
}
func (p repoPythonReader) dotted(node *ts.Node) string {
	if node == nil {
		return ""
	}
	if node.Type(p.lang) == pythonIdentifier {
		return p.identifier(node)
	}
	parts := []string{}
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		if child.Type(p.lang) == pythonIdentifier || child.Type(p.lang) == "dotted_name" {
			parts = append(parts, p.dotted(child))
		}
	}
	return strings.Join(parts, ".")
}
func (p repoPythonReader) importNode(node *ts.Node) repoPythonImport {
	result := repoPythonImport{from: node.Type(p.lang) == "import_from_statement", names: []string{}}
	module := node.ChildByFieldName("module_name", p.lang)
	if module != nil {
		result.module = p.dotted(module)
		result.relative = module.Type(p.lang) == "relative_import"
	}
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		if module != nil && child.StartByte() == module.StartByte() {
			continue
		}
		switch child.Type(p.lang) {
		case "aliased_import":
			result.names = append(result.names, p.dotted(child.ChildByFieldName("name", p.lang)))
		case "dotted_name":
			result.names = append(result.names, p.dotted(child))
		case "wildcard_import":
			result.names = append(result.names, "*")
		}
	}
	return result
}
func (p repoPythonReader) undecorate(node *ts.Node) *ts.Node {
	if node.Type(p.lang) == "decorated_definition" {
		return node.ChildByFieldName("definition", p.lang)
	}
	return node
}
func (p repoPythonReader) baseName(node *ts.Node) string {
	if node == nil {
		return ""
	}
	switch node.Type(p.lang) {
	case pythonParentheses:
		return p.baseName(pythonSingleChild(node, p.lang))
	case pythonIdentifier:
		return p.identifier(node)
	case "attribute":
		return p.identifier(node.ChildByFieldName("attribute", p.lang))
	case "subscript":
		return p.baseName(node.ChildByFieldName("value", p.lang))
	default:
		return ""
	}
}
func (p repoPythonReader) protocol(node *ts.Node) []string {
	bases := node.ChildByFieldName("superclasses", p.lang)
	if bases == nil {
		return nil
	}
	protocol := false
	for i := range bases.NamedChildCount() {
		protocol = protocol || p.baseName(bases.NamedChild(i)) == "Protocol"
	}
	if !protocol {
		return nil
	}
	result := []string{}
	body := node.ChildByFieldName("body", p.lang)
	for i := range body.NamedChildCount() {
		method := p.undecorate(body.NamedChild(i))
		if method.Type(p.lang) != "function_definition" || p.async(method) {
			continue
		}
		if p.untypedMethod(method) {
			result = append(result, p.identifier(node.ChildByFieldName("name", p.lang))+"."+p.identifier(method.ChildByFieldName("name", p.lang)))
		}
	}
	return result
}
func (p repoPythonReader) async(node *ts.Node) bool {
	for i := range node.ChildCount() {
		if node.Child(i).Type(p.lang) == "async" {
			return true
		}
	}
	return false
}
func (p repoPythonReader) untypedMethod(node *ts.Node) bool {
	if p.annotationAny(node.ChildByFieldName("return_type", p.lang)) {
		return true
	}
	params := node.ChildByFieldName("parameters", p.lang)
	for i := range params.NamedChildCount() {
		arg := params.NamedChild(i)
		annotation := arg.ChildByFieldName("type", p.lang)
		if annotation == nil {
			continue
		}
		name := arg.ChildByFieldName("name", p.lang)
		if name == nil {
			name = arg.NamedChild(0)
		}
		if name.Type(p.lang) == pythonIdentifier && p.identifier(name) == "self" {
			continue
		}
		if p.annotationAny(annotation) {
			return true
		}
	}
	return false
}
func (p repoPythonReader) annotationAny(node *ts.Node) bool {
	if node == nil {
		return false
	}
	if node.Type(p.lang) == pythonIdentifier {
		return p.identifier(node) == "Any"
	}
	for i := range node.NamedChildCount() {
		child := node.NamedChild(i)
		if node.Type(p.lang) == "keyword_argument" && i == 0 {
			continue
		}
		if node.Type(p.lang) == "lambda" && child.Type(p.lang) == "lambda_parameters" {
			if p.lambdaDefaultsAny(child) {
				return true
			}
			continue
		}
		if p.annotationAny(child) {
			return true
		}
	}
	return false
}
func (p repoPythonReader) lambdaDefaultsAny(node *ts.Node) bool {
	for i := range node.NamedChildCount() {
		if p.annotationAny(node.NamedChild(i).ChildByFieldName("value", p.lang)) {
			return true
		}
	}
	return false
}

func repoLayering(ctx context.Context, r *repository, rules []repoLayerRule, changed []string) ([]Finding, error) {
	result := []Finding{}
	for _, rule := range rules {
		problems, err := repoLayerFiles(ctx, r, rule, changed)
		if err != nil {
			return nil, err
		}
		result = append(result, problems...)
	}
	return result, nil
}
func repoLayerFiles(ctx context.Context, r *repository, rule repoLayerRule, changed []string) ([]Finding, error) {
	result := []Finding{}
	for _, name := range changed {
		if !strings.HasSuffix(name, ".py") || !pathPrefix(name, rule.root) || !r.file(name) {
			continue
		}
		facts, err := repoPython(ctx, r, name)
		if err != nil {
			return nil, err
		}
		for _, entry := range facts.imports {
			result = append(result, repoLayerImports(rule, entry, name)...)
		}
	}
	return result, nil
}
func repoLayerImports(rule repoLayerRule, entry repoPythonImport, name string) []Finding {
	names := entry.names
	if entry.from {
		names = []string{entry.module}
	}
	result := []Finding{}
	for _, imported := range names {
		if imported == rule.forbidden || strings.HasPrefix(imported, rule.forbidden+".") {
			result = append(result, finding("layering-rule-violation", rule.root+" must not import "+rule.forbidden+" (rule: "+rule.id+")", name))
		}
	}
	return result
}
