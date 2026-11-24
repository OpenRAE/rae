package governance

import (
	"context"
	"slices"

	"github.com/open-policy-agent/opa/v1/ast"
)

// preparePolicy compiles the unchanged policy with Conftest's exact OPA
// version. Evaluation is owned by the repository check after input admission.
// There is no external policy server or unverified executable.
func preparePolicy(ctx context.Context, modules map[string]string) (*ast.Compiler, error) {
	parsed := map[string]*ast.Module{}
	for name, source := range modules {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		module, err := ast.ParseModuleWithOpts(name, source, ast.ParserOptions{RegoVersion: ast.RegoV1, ProcessAnnotation: true})
		if err != nil {
			return nil, errRepoPolicyEvaluation
		}
		parsed[name] = module
	}
	capabilities := ast.CapabilitiesForThisVersion()
	capabilities.AllowNet = []string{}
	capabilities.Builtins = slices.DeleteFunc(capabilities.Builtins, func(builtin *ast.Builtin) bool {
		return slices.Contains([]string{"http.send", "net.lookup_ip_addr", "opa.runtime"}, builtin.Name)
	})
	compiler := ast.NewCompiler().WithEnablePrintStatements(true).WithCapabilities(capabilities)
	compiler.Compile(parsed)
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if compiler.Failed() {
		return nil, errRepoPolicyEvaluation
	}
	return compiler, nil
}
