package governance

import (
	"context"
	"encoding/json"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"strconv"
	"strings"

	"github.com/open-policy-agent/opa/v1/ast"
	"github.com/open-policy-agent/opa/v1/rego"
	"github.com/open-policy-agent/opa/v1/storage/inmem"
	opaprint "github.com/open-policy-agent/opa/v1/topdown/print"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type repoPolicyError string

func (e repoPolicyError) Error() string          { return string(e) }
func (repoPolicyError) Category() fault.Category { return fault.Operational }

const errRepoPolicyEvaluation = repoPolicyError("conftest repo policy evaluation failed")
const errRepoPolicyResult = repoPolicyError("conftest repo policy evaluation failed: the JSON result is invalid")

var repoPolicyRule = regexp.MustCompile(`^(?:deny|violation|warn)(?:_[a-zA-Z0-9]+)*\z`)

type policyDiscardPrint struct{}

func (policyDiscardPrint) Print(opaprint.Context, string) error { return nil }

func evaluateRepoRego(ctx context.Context, r *repository, input map[string]any) ([]Finding, error) {
	modules, err := repoRegoModules(r)
	if err != nil {
		return nil, err
	}
	compiler, err := preparePolicy(ctx, modules)
	if err != nil {
		return nil, err
	}
	rules, err := repoRegoRules(compiler)
	if err != nil {
		return nil, err
	}
	admitted, err := repoRegoInput(input)
	if err != nil {
		return nil, err
	}
	temporary, err := policyTemporaryDirectory("raes-conftest-input-")
	if err != nil {
		return nil, err
	}
	defer func() { _ = os.RemoveAll(temporary) }()
	data := map[string]any{"conftest": map[string]any{"file": map[string]any{"name": "repo-policy-input.json", "dir": temporary}}}
	findings := []Finding{}
	for _, rule := range rules {
		problems, queryErr := repoRegoRule(ctx, compiler, data, admitted, rule)
		if queryErr != nil {
			return nil, queryErr
		}
		findings = append(findings, problems...)
	}
	sortFindings(findings)
	return findings, nil
}

// Conftest unmarshals JSON numbers to float64 before supplying them to OPA.
func repoRegoInput(input map[string]any) (any, error) {
	encoded, err := json.Marshal(input)
	if err != nil {
		return nil, errRepoPolicyEvaluation
	}
	var admitted any
	if err = json.Unmarshal(encoded, &admitted); err != nil {
		return nil, errRepoPolicyEvaluation
	}
	return admitted, nil
}
func repoRegoRule(ctx context.Context, compiler *ast.Compiler, data map[string]any, input any, rule string) ([]Finding, error) {
	exception, err := repoRegoQuery(ctx, compiler, data, input, "data.main.exception[_][_] == "+strconv.Quote(repoRegoBareName(rule)))
	if err != nil {
		return nil, err
	}
	results, err := repoRegoQuery(ctx, compiler, data, input, "data.main."+rule)
	if err != nil {
		return nil, err
	}
	return repoRegoFindings(results, len(exception) > 0 || strings.HasPrefix(rule, "warn"))
}
func repoRegoBareName(rule string) string {
	if rule == "violation" || rule == "deny" || rule == "warn" {
		return ""
	}
	for _, prefix := range []string{"violation", "deny", "warn"} {
		rule = strings.TrimPrefix(rule, prefix+"_")
	}
	return rule
}

func repoRegoModules(r *repository) (map[string]string, error) {
	const root = "tools/policy/conftest"
	modules := map[string]string{}
	if err := repoRegoDirectory(r, root, map[string]bool{}, modules); err != nil {
		return nil, errRepoPolicyEvaluation
	}
	if len(modules) == 0 {
		return nil, errRepoPolicyEvaluation
	}
	return modules, nil
}

func repoRegoDirectory(r *repository, name string, active map[string]bool, modules map[string]string) error {
	resolved, err := r.resolve(name)
	if err != nil {
		return err
	}
	info, err := r.root.Stat(resolved)
	if err != nil {
		return err
	}
	if !info.IsDir() {
		if !strings.HasSuffix(name, ".rego") {
			return nil
		}
		if !info.Mode().IsRegular() {
			return errRepoPolicyEvaluation
		}
		source, readErr := r.text(name)
		if readErr != nil {
			return readErr
		}
		modules[name] = source
		return nil
	}
	if active[resolved] {
		return errRepoPolicyEvaluation
	}
	active[resolved] = true
	defer delete(active, resolved)
	entries, err := fs.ReadDir(r.root.FS(), resolved)
	if err != nil {
		return err
	}
	for _, entry := range entries {
		if err := repoRegoDirectory(r, name+"/"+entry.Name(), active, modules); err != nil {
			return err
		}
	}
	return nil
}
func repoRegoRules(compiler *ast.Compiler) ([]string, error) {
	names := []string{}
	for _, module := range compiler.Modules {
		rules, err := repoRegoModuleRules(module)
		if err != nil {
			return nil, err
		}
		for _, name := range rules {
			if !slices.ContainsFunc(names, func(previous string) bool { return strings.EqualFold(previous, name) }) {
				names = append(names, name)
			}
		}
	}
	slices.Sort(names)
	return names, nil
}
func repoRegoModuleRules(module *ast.Module) ([]string, error) {
	names := []string{}
	for _, rule := range module.Rules {
		if rule.Head == nil {
			continue
		}
		// Conftest refuses a failure object written with if but no contains.
		if rule.Head.Name == "" && rule.Head.Value != nil && len(rule.Head.Reference) > 0 && repoPolicyRule.MatchString(rule.Head.Reference[0].Value.String()) && rule.Head.Value.String() == trueLiteral {
			return nil, errRepoPolicyEvaluation
		}
		if module.Package.Path.String() == "data.main" && repoPolicyRule.MatchString(string(rule.Head.Name)) {
			names = append(names, string(rule.Head.Name))
		}
	}
	return names, nil
}

func repoRegoQuery(ctx context.Context, compiler *ast.Compiler, data map[string]any, input any, query string) (rego.ResultSet, error) {
	results, err := rego.New(rego.Query(query), rego.Compiler(compiler), rego.Store(inmem.NewFromObject(data)), rego.Input(input), rego.PrintHook(policyDiscardPrint{})).Eval(ctx)
	if cancelled := ctx.Err(); cancelled != nil {
		return nil, cancelled
	}
	if err != nil {
		return nil, errRepoPolicyEvaluation
	}
	return results, nil
}

func repoRegoFindings(results rego.ResultSet, ignored bool) ([]Finding, error) {
	findings := []Finding{}
	for _, result := range results {
		for _, expression := range result.Expressions {
			values, _ := expression.Value.([]any)
			problems, err := repoRegoValues(values, ignored)
			if err != nil {
				return nil, err
			}
			findings = append(findings, problems...)
		}
	}
	return findings, nil
}
func repoRegoValues(values []any, ignored bool) ([]Finding, error) {
	findings := []Finding{}
	for _, value := range values {
		message, known, err := repoRegoMessage(value)
		if err != nil {
			return nil, err
		}
		if !known || message == "" || ignored {
			continue
		}
		result, err := repoRegoFinding(value, message)
		if err != nil {
			return nil, err
		}
		findings = append(findings, result)
	}
	return findings, nil
}

func repoRegoMessage(value any) (string, bool, error) {
	switch value := value.(type) {
	case string:
		return value, true, nil
	case map[string]any:
		message, ok := value["msg"].(string)
		if !ok {
			return "", false, errRepoPolicyResult
		}
		return message, true, nil
	default:
		return "", false, nil // Conftest ignores set members without a message shape.
	}
}
func repoRegoFinding(value any, message string) (Finding, error) {
	result := Finding{RuleID: "conftest-policy-failure", Message: message}
	object, structured := value.(map[string]any)
	if !structured {
		return result, nil
	}
	if raw, present := object["rule_id"]; present {
		id, ok := raw.(string)
		if !ok {
			return Finding{}, errRepoPolicyResult
		}
		result.RuleID = id
	}
	switch selected := object["path"].(type) {
	case nil:
	case string:
		result.Path = &selected
	default:
		return Finding{}, errRepoPolicyResult
	}
	return result, nil
}

func policyTemporaryDirectory(prefix string) (string, error) {
	absolute, err := absoluteReferencePath(os.TempDir())
	if err != nil {
		return "", err
	}
	canonical, err := repositoryDirectory(absolute)
	if err != nil {
		return "", err
	}
	return os.MkdirTemp(filepath.Clean(canonical), prefix)
}
