package module

import (
	"cmp"
	"regexp"
	"strings"
)

const pepVersionPattern = `(?i)^v?(?:(?P<epoch>[0-9]+)!)?(?P<release>[0-9]+(?:\.[0-9]+)*)(?:[._-]?(?P<pre>alpha|beta|preview|pre|rc|a|b|c)[._-]?(?P<pre_n>[0-9]+)?)?(?:(?:-(?P<post_n1>[0-9]+))|(?:[._-]?(?P<post>post|rev|r)[._-]?(?P<post_n2>[0-9]+)?))?(?:[._-]?(?P<dev>dev)[._-]?(?P<dev_n>[0-9]+)?)?(?:\+(?P<local>[a-z0-9]+(?:[._-][a-z0-9]+)*))?$`

type pepVersion struct {
	epoch                                     string
	release                                   []string
	preKind, preNumber, postNumber, devNumber string
	hasPre, hasPost, hasDev                   bool
	local                                     []string
}
type versionStatus byte

const (
	versionInvalid versionStatus = iota
	versionValid
	versionDigits
)

func parsePEP(value string) (pepVersion, versionStatus) {
	pattern := regexp.MustCompile(pepVersionPattern)
	match := pattern.FindStringSubmatch(pythonTrim(value))
	if match == nil {
		return pepVersion{}, versionInvalid
	}
	groups := map[string]string{}
	for index, name := range pattern.SubexpNames() {
		if name != "" {
			groups[name] = strings.ToLower(match[index])
		}
	}
	version := pepVersion{epoch: decimalPart(groups["epoch"]), hasPre: groups["pre"] != "", hasPost: groups["post"] != "" || groups["post_n1"] != "", hasDev: groups["dev"] != ""}
	version.preKind = canonicalPre(groups["pre"])
	version.preNumber = decimalPart(groups["pre_n"])
	version.devNumber = decimalPart(groups["dev_n"])
	post := groups["post_n1"]
	if post == "" {
		post = groups["post_n2"]
	}
	version.postNumber = decimalPart(post)
	version.release = strings.Split(groups["release"], ".")
	for i, part := range version.release {
		version.release[i] = decimalPart(part)
	}
	if groups["local"] != "" {
		version.local = strings.FieldsFunc(groups["local"], func(r rune) bool { return r == '.' || r == '_' || r == '-' })
		for i, part := range version.local {
			if decimalLabel(part) {
				version.local[i] = decimalPart(part)
			}
		}
	}
	if numericOverflow(groups) {
		return version, versionDigits
	}
	return version, versionValid
}
func numericOverflow(groups map[string]string) bool {
	for _, key := range []string{"epoch", "pre_n", "post_n1", "post_n2", "dev_n"} {
		if len(groups[key]) > 4300 {
			return true
		}
	}
	for part := range strings.SplitSeq(groups["release"], ".") {
		if len(part) > 4300 {
			return true
		}
	}
	for _, part := range strings.FieldsFunc(groups["local"], func(r rune) bool { return r == '.' || r == '_' || r == '-' }) {
		if decimalLabel(part) && len(part) > 4300 {
			return true
		}
	}
	return false
}
func decimalPart(s string) string {
	s = strings.TrimLeft(s, "0")
	if s == "" {
		return "0"
	}
	return s
}
func decimalLabel(s string) bool { return s != "" && strings.Trim(s, "0123456789") == "" }
func decimalOrder(a, b string) int {
	if len(a) != len(b) {
		return cmp.Compare(len(a), len(b))
	}
	return strings.Compare(a, b)
}
func canonicalPre(s string) string {
	switch s {
	case "alpha":
		return "a"
	case "beta":
		return "b"
	case "preview", "pre", "c":
		return "rc"
	default:
		return s
	}
}
func (v pepVersion) compare(other pepVersion, local bool) int {
	if order := v.baseCompare(other); order != 0 {
		return order
	}
	if order := cmp.Compare(v.preRank(), other.preRank()); order != 0 {
		return order
	}
	if v.hasPre {
		if order := strings.Compare(v.preKind, other.preKind); order != 0 {
			return order
		}
		if order := decimalOrder(v.preNumber, other.preNumber); order != 0 {
			return order
		}
	}
	if order := optionalNumber(v.hasPost, v.postNumber, other.hasPost, other.postNumber, false); order != 0 {
		return order
	}
	if order := optionalNumber(v.hasDev, v.devNumber, other.hasDev, other.devNumber, true); order != 0 {
		return order
	}
	if local {
		return localOrder(v.local, other.local)
	}
	return 0
}
func (v pepVersion) baseCompare(other pepVersion) int {
	if order := decimalOrder(v.epoch, other.epoch); order != 0 {
		return order
	}
	for i := range max(len(v.release), len(other.release)) {
		a, b := "0", "0"
		if i < len(v.release) {
			a = v.release[i]
		}
		if i < len(other.release) {
			b = other.release[i]
		}
		if order := decimalOrder(a, b); order != 0 {
			return order
		}
	}
	return 0
}
func (v pepVersion) preRank() int {
	if v.hasPre {
		return 0
	}
	if !v.hasPost && v.hasDev {
		return -1
	}
	return 1
}
func optionalNumber(aPresent bool, a string, bPresent bool, b string, absentHigh bool) int {
	if aPresent != bPresent {
		order := 1
		if !aPresent {
			order = -1
		}
		if absentHigh {
			order = -order
		}
		return order
	}
	if aPresent {
		return decimalOrder(a, b)
	}
	return 0
}
func localOrder(a, b []string) int {
	for i := range min(len(a), len(b)) {
		aNumber, bNumber := decimalLabel(a[i]), decimalLabel(b[i])
		if aNumber != bNumber {
			if aNumber {
				return 1
			}
			return -1
		}
		order := strings.Compare(a[i], b[i])
		if aNumber {
			order = decimalOrder(a[i], b[i])
		}
		if order != 0 {
			return order
		}
	}
	return cmp.Compare(len(a), len(b))
}
func (v pepVersion) canonical() string {
	var out strings.Builder
	if v.epoch != "0" {
		out.WriteString(v.epoch + "!")
	}
	out.WriteString(strings.Join(v.release, "."))
	if v.hasPre {
		out.WriteString(v.preKind + v.preNumber)
	}
	if v.hasPost {
		out.WriteString(".post" + v.postNumber)
	}
	if v.hasDev {
		out.WriteString(".dev" + v.devNumber)
	}
	if len(v.local) > 0 {
		out.WriteString("+" + strings.Join(v.local, "."))
	}
	return out.String()
}
func (v pepVersion) prefix(other pepVersion, components int) bool {
	if v.epoch != other.epoch {
		return false
	}
	for i := range components {
		part := "0"
		if i < len(v.release) {
			part = v.release[i]
		}
		if part != other.release[i] {
			return false
		}
	}
	return true
}
func (v pepVersion) prerelease() bool { return v.hasPre || v.hasDev }
func (v pepVersion) plainRelease() bool {
	return !v.hasPre && !v.hasPost && !v.hasDev && len(v.local) == 0
}
