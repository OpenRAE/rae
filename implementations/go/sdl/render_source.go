package sdl

import (
	"context"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
)

// RenderSource renders an admitted native model through the existing strict
// formatter. It grants no filesystem or import authority.
func RenderSource(ctx context.Context, scenario Scenario) ([]byte, error) {
	if err := checkParsingContext(ctx); err != nil {
		return nil, err
	}
	owned, err := nativeScenario(scenario)
	if err != nil || !owned.document.Validated() {
		return nil, invalidScenario()
	}
	rendered, err := owned.parser.FormatContext(ctx, authoring.Request{Source: owned.document.JSON()})
	if err != nil {
		return nil, err
	}
	if len(rendered.Diagnostics) != 0 {
		return nil, invalidScenario()
	}
	return rendered.Content, nil
}
