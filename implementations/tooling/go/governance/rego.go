package governance

import (
	"context"
	"sort"

	"github.com/open-policy-agent/opa/v1/rego"
)

// preparePolicy compiles the unchanged policy with Conftest's exact OPA
// version. Evaluation is owned by the repository check after input admission.
// There is no external policy server or unverified executable.
func preparePolicy(ctx context.Context, modules map[string]string) (rego.PreparedEvalQuery, error) {
	options := []func(*rego.Rego){rego.Query("data.main.deny")}
	names := make([]string, 0, len(modules))
	for name := range modules {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		options = append(options, rego.Module(name, modules[name]))
	}
	return rego.New(options...).PrepareForEval(ctx)
}
