package governance

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestCheckCancellationDuringClock(t *testing.T) {
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	_, err := Check(ctx, Request{Tool: "pr-title", Title: "feat: validate cancellation", Clock: func() time.Time {
		cancel()
		return time.Date(2026, time.November, 7, 0, 0, 0, 0, time.UTC)
	}})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("canceled evaluation returned a policy verdict: %v", err)
	}
}
