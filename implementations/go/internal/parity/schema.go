package parity

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

// schemaRunner retains compiler errors as harness failures, not invalid inputs.
func schemaRunner() Runner {
	validator, loadErr := validation.New(nil)
	return func(_ context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		if len(c.Args) != 1 {
			return nil, errors.New("schema runner: expected one contract id")
		}
		data, ok := c.Files["payload.json"]
		if !ok {
			return nil, errors.New("schema runner: missing payload.json")
		}
		// This is the trusted recorded schema surface. The corpus loader already
		// bounds each input to 64 MiB; runtime adapters select their own limits.
		_, err := validator.DecodeSchema(c.Args[0], data, ingress.Limits{MaxBytes: 67108864, MaxDepth: 1024})
		if category, ok := fault.CategoryOf(err); err != nil && (!ok || category != fault.InvalidInput) {
			return nil, err
		}
		return json.Marshal(struct {
			Valid bool `json:"valid"`
		}{err == nil})
	}
}
