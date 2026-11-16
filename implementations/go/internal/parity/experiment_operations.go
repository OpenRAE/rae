package parity

import (
	"context"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// The recorded MCP adapter removes non-JSON human text through machine_text.
// This adapter exercises the native experiment parser and retains that wire
// projection. Native constructor and refusal fixtures check the precise result.
func experimentValidateRunner() Runner {
	return func(ctx context.Context, c Case) (json.RawMessage, error) {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		var args map[string]json.RawMessage
		if json.Unmarshal(c.Files["arguments.json"], &args) != nil {
			return nil, fault.New(fault.InvalidInput, "parity-arguments-invalid", nil)
		}
		var content string
		raw, present := args["spec_content"]
		if !present || string(raw) == termNull || json.Unmarshal(raw, &content) != nil {
			return json.Marshal(map[string]any{"is_error": true})
		}
		_, err := admission.ParseExperiment([]byte(content), nil)
		if err != nil {
			if category, known := fault.CategoryOf(err); !known || category != fault.InvalidInput {
				return nil, err
			}
		}
		return json.Marshal(map[string]any{termContent: []any{map[string]any{"type": termText, termText: nil}}, "is_error": false, "structured_content": map[string]any{"result": nil}})
	}
}
