package clock

import (
	"testing"
	"time"
)

func TestInjectedClockIsReadAtEachCallAndNormalizedToUTC(t *testing.T) {
	calls := 0
	fixed := time.Date(2024, 1, 1, 5, 30, 0, 0, time.FixedZone("offset", 19800))
	injected := func() time.Time { calls++; return fixed }
	for range 2 {
		got := Read(injected)
		if !got.Equal(fixed) || got.Location() != time.UTC {
			t.Errorf("Read(injected) = %v, want the same instant in UTC", got)
		}
	}
	if calls != 2 {
		t.Errorf("clock calls = %d, want 2", calls)
	}
	before := System()
	got := Read(nil)
	after := System()
	if got.Before(before) || got.After(after) || got.Location() != time.UTC {
		t.Errorf("Read(nil) = %v, want a current UTC wall-clock instant", got)
	}
}
