package trial

import (
	"context"
	"errors"
	"log/slog"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

//nolint:ireturn // The type parameter retains each exact owner result type.
func installedTrialOwner[T any](ctx context.Context, work func() (T, error)) (result T, err error) {
	defer func() {
		if recover() != nil {
			slog.ErrorContext(ctx, "installed trial owner failed", slog.String("failure_class", "panic"))
			err = fault.New(fault.Operational, "trial-owner-failed", nil)
		}
	}()
	if err = ctx.Err(); err != nil {
		return result, err
	}
	result, err = work()
	if ctx.Err() != nil {
		return result, ctx.Err()
	}
	if err == nil {
		return result, nil
	}
	if owned, ok := errors.AsType[*fault.Error](err); ok {
		return result, fault.New(owned.Category(), owned.Code(), nil)
	}
	slog.ErrorContext(ctx, "installed trial owner failed", slog.String("failure_class", "foreign"))
	return result, fault.New(fault.Operational, "trial-owner-failed", nil)
}
func configurationContextForScenario(ctx context.Context, factory ControlContextFactory, selected sdl.Scenario) (admission.ParticipantControlContextValidator, error) { //nolint:ireturn // Installed hook returns the public admitted context interface.
	return installedTrialOwner(ctx, func() (admission.ParticipantControlContextValidator, error) {
		return factory.ForScenario(ctx, selected)
	})
}
