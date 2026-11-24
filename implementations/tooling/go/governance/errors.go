package governance

import (
	"errors"
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func (policyInputError) Category() fault.Category { return fault.InvalidInput }
func (requirementError) Category() fault.Category { return fault.InvalidInput }
func (scopeError) Category() fault.Category       { return fault.InvalidInput }

func classifyPolicyError(err error) error {
	if err == nil {
		return nil
	}
	if _, known := fault.CategoryOf(err); known {
		return err
	}
	if _, pathError := errors.AsType[*fs.PathError](err); pathError {
		return fault.New(fault.Operational, "repository-policy-read", err)
	}
	if errors.Is(err, errNotUTF8) || errors.Is(err, errUnsafePath) {
		return fault.New(fault.InvalidInput, "repository-policy-input", err)
	}
	return err
}
