package a

import (
	"errors"
	"fmt"
)

var errSentinel = errors.New("sentinel")

func Wrap(err error, name string) []error {
	return []error{
		fmt.Errorf("read %s: %w", name, err),
		fmt.Errorf("%w: %s", errSentinel, name),
		fmt.Errorf("%w: read %s: %w", errSentinel, name, err),
		fmt.Errorf("read %w from %s", err, name), // want `place %w at the start or the end of the error format`
		fmt.Errorf("read %[1]w again: %[2]s", err, name), // want `place %w at the start or the end of the error format`
		fmt.Errorf("100%% done: %w", err),
		fmt.Errorf("literal %%w then %s", name),
		fmt.Errorf("%s %v", name, err),
		fmt.Errorf("incomplete %", name),
		Errorf("read %w from %s", err, name),
	}
}

func Errorf(format string, args ...any) error {
	return fmt.Errorf(format, args...)
}
