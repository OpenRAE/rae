// Package clock owns injected wall-clock reads (ADR-118).
// Wall time is neither semantic time nor a monotonic execution watchdog.
package clock

import "time"

// Clock supplies a wall-clock instant to its owner.
type Clock func() time.Time

// System is the sole direct wall-clock read. Applications inject a Clock into
// each time-reading owner; tests supply a fixed function.
func System() time.Time { return time.Now().UTC() }

// Read reads an injected clock in UTC. A nil clock selects the system default.
func Read(clock Clock) time.Time {
	if clock == nil {
		clock = System
	}
	return clock().UTC()
}
