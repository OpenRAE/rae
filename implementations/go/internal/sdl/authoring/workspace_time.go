package authoring

import (
	"regexp"
	"strconv"
	"strings"
	"time"
)

var (
	workspaceDate     = regexp.MustCompile(`^[0-9]{4}-[0-9]{2}-[0-9]{2}$`)
	workspaceDateTime = regexp.MustCompile(`^([0-9]{4})-([0-9][0-9]?)-([0-9][0-9]?)(?:[Tt]|[ \t]+)([0-9][0-9]?):([0-9]{2}):([0-9]{2})(?:\.([0-9]*))?(?:[ \t]*(Z|([-+])([0-9][0-9]?)(?::([0-9]{2}))?))?$`)
)

func workspaceTimestamp(raw string) (bool, error) {
	if workspaceDate.MatchString(raw) {
		return true, workspaceDateParts(strings.Split(raw, "-"))
	}
	parts := workspaceDateTime.FindStringSubmatch(raw)
	if parts == nil {
		return false, nil
	}
	if err := workspaceDateParts(parts[1:4]); err != nil {
		return true, err
	}
	hours, minutes, seconds := workspaceDecimal(parts[4]), workspaceDecimal(parts[5]), workspaceDecimal(parts[6])
	if hours > 23 || minutes > 59 || seconds > 59 {
		return true, invalid()
	}
	if parts[10] != "" && workspaceDecimal(parts[10])*60+workspaceDecimal(parts[11]) >= 24*60 {
		return true, invalid()
	}
	return true, nil
}
func workspaceDateParts(parts []string) error {
	year, month, day := workspaceDecimal(parts[0]), workspaceDecimal(parts[1]), workspaceDecimal(parts[2])
	date := time.Date(year, time.Month(month), day, 0, 0, 0, 0, time.UTC)
	if year < 1 || date.Year() != year || int(date.Month()) != month || date.Day() != day {
		return invalid()
	}
	return nil
}
func workspaceDecimal(raw string) int {
	if raw == "" {
		return 0
	}
	number, err := strconv.Atoi(raw)
	if err != nil {
		return -1
	}
	return number
}
