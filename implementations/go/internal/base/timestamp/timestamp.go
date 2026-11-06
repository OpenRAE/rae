// Package timestamp owns the four named timestamp policies of ADR-118.
// It keeps microsecond precision and offsets, including fractional ISO offsets.
package timestamp

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// ErrInput reports invalid timestamp text.
var ErrInput = fault.New(fault.InvalidInput, "timestamp", nil)

// ErrLeap reports a leap-second spelling outside the governed leap instants.
var ErrLeap = fault.New(fault.InvalidInput, "timestamp-leap-second", ErrInput)

const utcOffset = "+00:00"

// Time retains the authored local time and exact UTC offset. The Go time
// package's Location cannot represent a fractional-second offset.
type Time struct {
	local  time.Time
	offset time.Duration
}

var (
	datePrefix = regexp.MustCompile("^[0-9]{4}(?:-[0-9]{2}-[0-9]{2}|[0-9]{4}|-W[0-9]{2}(?:-[1-7])?|W[0-9]{2}[1-7]?)")
	rfc3339    = regexp.MustCompile(`^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt](?:[01][0-9]|2[0-3]):[0-5][0-9]:(?:[0-5][0-9]|60)(?:\.[0-9]+)?(?:[Zz]|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])$`)
)

// Offset returns the authored UTC offset.
func (t Time) Offset() time.Duration { return t.offset }

// Instant returns the UTC instant, without discarding fractional offsets.
func (t Time) Instant() time.Time { return t.local.Add(-t.offset) }

// String writes Python's isoformat_z text, at microsecond precision.
func (t Time) String() string {
	text := formatLocal(t.local)
	sign, offset := "+", t.offset
	if offset < 0 {
		sign, offset = "-", -offset
	}
	hours := offset / time.Hour
	minutes := offset % time.Hour / time.Minute
	seconds := offset % time.Minute / time.Second
	text += fmt.Sprintf("%s%02d:%02d", sign, hours, minutes)
	micros := offset % time.Second / time.Microsecond
	if seconds != 0 || micros != 0 {
		text += fmt.Sprintf(":%02d", seconds)
	}
	if micros != 0 {
		text += fmt.Sprintf(".%06d", micros)
	}
	// Retain isoformat_z's literal replacement, including second offsets.
	return strings.ReplaceAll(text, utcOffset, "Z")
}

// Format writes an aware Go instant with Python's automatic microsecond text.
func Format(t time.Time) string {
	_, offset := t.Zone()
	local := time.Date(t.Year(), t.Month(), t.Day(), t.Hour(), t.Minute(), t.Second(), t.Nanosecond(), time.UTC)
	return (Time{local: local, offset: time.Duration(offset) * time.Second}).String()
}

func formatLocal(t time.Time) string {
	t = t.Truncate(time.Microsecond)
	layout := "2006-01-02T15:04:05"
	if t.Nanosecond() != 0 {
		layout += ".000000"
	}
	return t.Format(layout)
}

// ParseRFC3339 applies the governed grammar, preserving the offset and rolling
// a real UTC leap second forward by one second.
func ParseRFC3339(field, text string) (Time, error) {
	if !rfc3339.MatchString(text) {
		return Time{}, fmt.Errorf("%s must be a valid RFC 3339 date-time: %w", field, ErrInput)
	}
	leap := text[17:19] == "60"
	normalized := strings.ToUpper(text)
	if leap {
		normalized = normalized[:17] + "59" + normalized[19:]
	}
	parsed, _, err := parseISO(normalized)
	if err != nil {
		return Time{}, fmt.Errorf("%s must be a valid RFC 3339 date-time: %w", field, ErrInput)
	}
	if leap {
		utc := parsed.Instant()
		if utc.Hour() != 23 || utc.Minute() != 59 || utc.Second() != 59 || !leapDate(utc.Format("2006-01-02")) {
			return Time{}, fmt.Errorf("%s must use a valid RFC 3339 leap-second instant: %w", field, ErrLeap)
		}
		parsed.local = parsed.local.Add(time.Second)
	}
	return parsed, nil
}

func leapDate(date string) bool {
	const dates = "|1972-06-30|1972-12-31|1973-12-31|1974-12-31|1975-12-31|1976-12-31|1977-12-31|1978-12-31|1979-12-31|1981-06-30|1982-06-30|1983-06-30|1985-06-30|1987-12-31|1989-12-31|1990-12-31|1992-06-30|1993-06-30|1994-06-30|1995-12-31|1997-06-30|1998-12-31|2005-12-31|2008-12-31|2012-06-30|2015-06-30|2016-12-31|"
	return strings.Contains(dates, "|"+date+"|")
}

// ParseOffsetUTC requires an explicit offset and returns UTC. Lowercase z is
// refused by this policy, as in Python's datetime.fromisoformat.
func ParseOffsetUTC(text string) (Time, error) {
	parsed, aware, err := parseISO(text)
	if err != nil || !aware {
		return Time{}, ErrInput
	}
	utc := parsed.Instant()
	if utc.Year() < 1 || utc.Year() > 9999 {
		return Time{}, ErrInput
	}
	return Time{local: utc}, nil
}

// ParseOffset requires an explicit offset, accepting Z and z and keeping it.
func ParseOffset(field, text string) (Time, error) {
	text = strings.NewReplacer("Z", utcOffset, "z", utcOffset).Replace(text)
	parsed, aware, err := parseISO(text)
	if err != nil || !aware {
		return Time{}, fmt.Errorf("%s must be an ISO 8601 date-time with an explicit UTC offset: %w", field, ErrInput)
	}
	return parsed, nil
}

// ParseAssumingUTC treats date-only and naive ISO values as UTC.
func ParseAssumingUTC(text string) (Time, error) {
	parsed, _, err := parseISO(text)
	return parsed, err
}

func parseISO(text string) (Time, bool, error) {
	if !utf8.ValidString(text) {
		return Time{}, false, ErrInput
	}
	date := datePrefix.FindString(text)
	local, err := parseDate(date)
	if err != nil {
		return Time{}, false, err
	}
	if len(text) == len(date) {
		return Time{local: local}, false, nil
	}
	_, size := utf8.DecodeRuneInString(text[len(date):])
	clockText, zone, aware := splitOffset(text[len(date)+size:])
	clock, err := parseClock(clockText, false)
	if err != nil {
		return Time{}, false, err
	}
	var offset time.Duration
	if zone != "" {
		offset, err = parseClock(zone, true)
		if err != nil {
			return Time{}, false, err
		}
	}
	local = local.Add(clock)
	if local.Year() > 9999 {
		return Time{}, false, ErrInput
	}
	return Time{local: local, offset: offset}, aware, nil
}

func splitOffset(text string) (clock, zone string, aware bool) {
	if clock, found := strings.CutSuffix(text, "Z"); found {
		return clock, "", true
	}
	index := strings.IndexAny(text, "+-")
	if index == -1 {
		return text, "", false
	}
	return text[:index], text[index:], true
}

func parseDate(text string) (time.Time, error) {
	if strings.Contains(text, "W") {
		return parseWeekDate(text)
	}
	layout := "2006-01-02"
	if len(text) == 8 {
		layout = "20060102"
	}
	date, err := time.Parse(layout, text)
	if err != nil || date.Year() < 1 {
		return time.Time{}, ErrInput
	}
	return date, nil
}

func parseWeekDate(text string) (time.Time, error) {
	digits := strings.ReplaceAll(strings.ReplaceAll(text, "-", ""), "W", "")
	year, _ := strconv.Atoi(digits[:4])
	week, _ := strconv.Atoi(digits[4:6])
	day := 1
	if len(digits) == 7 {
		day, _ = strconv.Atoi(digits[6:])
	}
	january := time.Date(year, time.January, 4, 0, 0, 0, 0, time.UTC)
	monday := january.AddDate(0, 0, -(int(january.Weekday())+6)%7)
	date := monday.AddDate(0, 0, (week-1)*7+day-1)
	actualYear, actualWeek := date.ISOWeek()
	if year < 1 || actualYear != year || actualWeek != week || date.Year() > 9999 {
		return time.Time{}, ErrInput
	}
	return date, nil
}

func parseClock(text string, offset bool) (time.Duration, error) {
	negative := offset && strings.HasPrefix(text, "-")
	if offset {
		// splitOffset supplies a nonempty signed zone.
		text = text[1:]
	}
	whole, fraction, err := splitFraction(text)
	if err != nil {
		return 0, err
	}

	digits := strings.ReplaceAll(whole, ":", "")
	if !validClock(whole, digits, fraction != "") {
		return 0, ErrInput
	}
	hour, minute, second := clockParts(digits)
	if !offset && (hour > 24 || minute > 59 || second > 59) {
		return 0, ErrInput
	}
	duration := time.Duration(hour)*time.Hour + time.Duration(minute)*time.Minute + time.Duration(second)*time.Second
	if fraction != "" {
		microseconds, _ := strconv.Atoi((fraction + "000000")[:6])
		duration += time.Duration(microseconds) * time.Microsecond
	}
	if !offset && duration > 24*time.Hour || offset && duration >= 24*time.Hour {
		return 0, ErrInput
	}
	if negative {
		return -duration, nil
	}
	return duration, nil
}

func validClock(whole, digits string, fraction bool) bool {
	if strings.Trim(digits, "0123456789") != "" || len(digits) != 2 && len(digits) != 4 && len(digits) != 6 {
		return false
	}
	if fraction && len(digits) != 6 {
		return false
	}
	if !strings.Contains(whole, ":") {
		return true
	}
	return len(whole) == 5 && whole[2] == ':' || len(whole) == 8 && whole[2] == ':' && whole[5] == ':'
}

func splitFraction(text string) (whole, fraction string, err error) {
	index := strings.IndexAny(text, ".,")
	if index == -1 {
		return text, "", nil
	}
	whole, fraction = text[:index], text[index+1:]
	if fraction == "" || strings.Trim(fraction, "0123456789") != "" {
		return "", "", ErrInput
	}
	return whole, fraction, nil
}

func clockParts(digits string) (hour, minute, second int) {
	hour, _ = strconv.Atoi(digits[:2])
	if len(digits) >= 4 {
		minute, _ = strconv.Atoi(digits[2:4])
	}
	if len(digits) == 6 {
		second, _ = strconv.Atoi(digits[4:])
	}
	return hour, minute, second
}
