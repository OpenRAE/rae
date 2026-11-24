package admission

import (
	"encoding/json"
	"regexp"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

var variableReference = regexp.MustCompile(`^\$\{(?:(?:[a-z0-9][a-z0-9_-]{0,63}|__private)\.)*[a-z0-9][a-z0-9_-]{0,63}\}$`)

func variableRef(v string) bool { return variableReference.MatchString(v) }
func serviceMaterialization(invocation validation.Invocation) error {
	data, err := json.Marshal(sdlInstance(invocation))
	if err != nil {
		return invalid()
	}
	findings, err := sdlrules.ServiceMaterialization(data, nil)
	if err != nil || len(findings) > 0 {
		return invalid()
	}
	return nil
}
