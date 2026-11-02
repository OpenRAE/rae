package timestamp

import (
	"errors"
	"testing"
	"time"
)

func TestNamedTimestampPoliciesMatchPython(t *testing.T) {
	tests := []struct {
		mode, input, want string
	}{
		{"rfc3339", "2024-01-01t00:00:00z", "2024-01-01T00:00:00Z"},
		{"rfc3339", "2024-01-01T05:30:00.25+05:30", "2024-01-01T05:30:00.250000+05:30"},
		{"rfc3339", "2016-12-31T23:59:60Z", "2017-01-01T00:00:00Z"},
		{"rfc3339", "2017-01-01T05:29:60+05:30", "2017-01-01T05:30:00+05:30"},
		{"rfc3339", "1972-06-30T23:59:60.1234567Z", "1972-07-01T00:00:00.123456Z"},
		{"utc", "2024-01-01T05:00:00+05:00", "2024-01-01T00:00:00Z"},
		{"utc", "2024-01-01T00:00:00-01:30", "2024-01-01T01:30:00Z"},
		{"offset", "2024-01-01T00:00:00z", "2024-01-01T00:00:00Z"},
		{"offset", "2024-01-01T00:00:00+00:00:30.5", "2024-01-01T00:00:00Z:30.500000"},
		{"offset", "2024-01-01T00:00:00+00:00:00.5", "2024-01-01T00:00:00Z:00.500000"},
		{"offset", "2024-01-01T00:00:00+01:99", "2024-01-01T00:00:00+02:39"},
		{"assuming", "2024-01-01", "2024-01-01T00:00:00Z"},
		{"utc", "0001-01-01T00:00:00Z", "0001-01-01T00:00:00Z"},
		{"utc", "9999-12-31T23:59:59Z", "9999-12-31T23:59:59Z"},
		{"assuming", "0001-01-01", "0001-01-01T00:00:00Z"},
		{"assuming", "0001-W01-1", "0001-01-01T00:00:00Z"},
		{"assuming", "9999-W01-1", "9999-01-04T00:00:00Z"},
		{"assuming", "2024-01-01T24:00", "2024-01-02T00:00:00Z"},
		{"assuming", "2024-01-01T24:00:00.0000001", "2024-01-02T00:00:00Z"},
		{"assuming", "20240101T123456,000006", "2024-01-01T12:34:56.000006Z"},
		{"assuming", "2024-W01", "2024-01-01T00:00:00Z"},
		{"assuming", "2024W011", "2024-01-01T00:00:00Z"},
		{"assuming", "2020-W53-7T12:34", "2021-01-03T12:34:00Z"},
		{"assuming", "2024-01-01☃12", "2024-01-01T12:00:00Z"},
		{"assuming", "2024-01-01T12:34:56.123456789", "2024-01-01T12:34:56.123456Z"},
	}
	for _, test := range tests {
		got, err := parseForTest(test.mode, test.input)
		if err != nil || got.String() != test.want {
			t.Errorf("%s(%q) = %s, %v, want %s", test.mode, test.input, got.String(), err, test.want)
		}
	}
	offset, err := ParseOffset("at", "2024-01-01T00:00:00+00:00:30.5")
	want := time.Date(2023, 12, 31, 23, 59, 29, 500000000, time.UTC)
	if err != nil || offset.Offset() != 30500*time.Millisecond || !offset.Instant().Equal(want) {
		t.Errorf("fractional offset instant = %v, %v, want %v", offset.Instant(), err, want)
	}
}

func parseForTest(mode, input string) (Time, error) {
	switch mode {
	case "rfc3339":
		return ParseRFC3339("at", input)
	case "utc":
		return ParseOffsetUTC(input)
	case "offset":
		return ParseOffset("at", input)
	default:
		return ParseAssumingUTC(input)
	}
}

func TestTimestampRefusalsAndRangeBoundaries(t *testing.T) {
	for _, test := range [][2]string{
		{"rfc3339", "2015-12-31T23:59:60Z"},
		{"rfc3339", "2016-12-31T22:59:60Z"},
		{"rfc3339", "2024-02-30T00:00:00Z"},
		{"rfc3339", "2024-01-01 00:00:00Z"},
		{"rfc3339", "2024-01-01T00:00:00"},
		{"utc", "2024-01-01"}, {"utc", "2024-01-01T00:00:00z"},
		{"utc", "0001-01-01T00:00:00+01:00"},
		{"utc", "9999-12-31T23:59:59-01:00"},
		{"offset", "2024-01-01T00:00:00"},
		{"assuming", ""}, {"assuming", "2024-02-30"},
		{"assuming", "0000-01-01"}, {"assuming", "0000-W01-1"}, {"assuming", "9999-W52-7"}, {"assuming", "2021-W53-1"},
		{"assuming", "2024-W011"}, {"assuming", "2024-01-01T24:00:00.000001"},
		{"assuming", "2024-01-01T24:00:01"}, {"assuming", "2024-01-01T25:00"},
		{"assuming", "9999-12-31T24:00"},
		{"assuming", "2024-01-01T12:60"}, {"assuming", "2024-01-01T12:34:60"},
		{"assuming", "2024-01-01T12:34.5"}, {"assuming", "2024-01-01T12:3456"},
		{"assuming", "2024-01-01T12:34:56."}, {"assuming", "2024-01-01T12:34:56.x"},
		{"assuming", "2024-01-01T12:34:56+24:00"},
		{"assuming", "2024-01-01T12:34:56+-01:00"},
		{"assuming", "\xff"},
	} {
		if _, err := parseForTest(test[0], test[1]); !errors.Is(err, ErrInput) {
			t.Errorf("%s(%q) error = %v, want invalid timestamp", test[0], test[1], err)
		}
	}
	if _, err := ParseRFC3339("at", "2015-12-31T23:59:60Z"); !errors.Is(err, ErrLeap) {
		t.Errorf("invalid leap second error = %v, want ErrLeap", err)
	}
}

func TestFormatKeepsAutomaticPrecisionAndSecondOffsets(t *testing.T) {
	for _, test := range []struct {
		input time.Time
		want  string
	}{
		{time.Date(2024, 1, 2, 3, 4, 5, 0, time.UTC), "2024-01-02T03:04:05Z"},
		{time.Date(2024, 1, 2, 3, 4, 5, 6000, time.UTC), "2024-01-02T03:04:05.000006Z"},
		{time.Date(2024, 1, 2, 3, 4, 5, 123456789, time.FixedZone("offset", -123)), "2024-01-02T03:04:05.123456-00:02:03"},
	} {
		if got := Format(test.input); got != test.want {
			t.Errorf("Format(%v) = %s, want %s", test.input, got, test.want)
		}
	}
}
