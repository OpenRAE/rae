package timestamp

import "testing"

func FuzzNamedTimestampPolicies(f *testing.F) {
	for _, text := range []string{"2024-01-01T00:00:00Z", "2016-12-31T23:59:60Z", "2024-W01", "2024-01-01T24:00", "2024-01-01T00:00:00+00:00:30.5", "", "\xff"} {
		f.Add(text)
	}
	f.Fuzz(func(t *testing.T, text string) {
		if len(text) > 4096 {
			t.Skip()
		}
		if parsed, err := ParseRFC3339("at", text); err == nil {
			again, failure := ParseRFC3339("at", parsed.String())
			if failure != nil || !again.Instant().Equal(parsed.Instant()) {
				t.Errorf("RFC3339 normalization changed an instant: %v", failure)
			}
		}
		// Exercise the wider grammars independently: some reference output
		// spellings (fractional offsets) are intentionally not RFC 3339 text.
		_, _ = ParseOffsetUTC(text)
		_, _ = ParseOffset("at", text)
		_, _ = ParseAssumingUTC(text)
	})
}
