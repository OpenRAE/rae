package parity

import (
	"context"
	"encoding/json"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/admission"
)

// portableAdmissionRunner compares the library's admission decision. This is
// a projection of portable CLI goldens, not a claim to implement that command.
func portableAdmissionRunner() Runner {
	validator, loadErr := admission.New()
	return func(_ context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		if len(c.Args) != 1 {
			return nil, errors.New("contract admission: expected one contract id")
		}
		data, ok := c.Files["payload.json"]
		if !ok {
			return nil, errors.New("contract admission: missing payload.json")
		}
		err := validator.CheckPortable(c.Args[0], data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
		if category, typed := fault.CategoryOf(err); err != nil && (!typed || category != fault.InvalidInput) {
			return nil, err
		}
		return json.Marshal(struct {
			Admitted bool `json:"admitted"`
		}{err == nil})
	}
}
