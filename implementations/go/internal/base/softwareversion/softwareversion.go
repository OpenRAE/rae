// Package softwareversion evaluates the closed installed version relations.
// Unrecognized semantic identities remain unsupported, never guessed.
package softwareversion

import (
	"cmp"
	"encoding/json"
	"math/big"
	"regexp"
	"slices"
	"strconv"
	"strings"
	"unicode/utf8"

	rpm "github.com/knqyf263/go-rpm-version"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// ErrInput reports an invalid endpoint, relation name or empty interval.
var ErrInput = fault.New(fault.InvalidInput, "version-domain", nil)

// Relation is the exact installed semantic identity.
type Relation struct {
	Authority, ID, Revision, Digest string
}

// Membership distinguishes lack of knowledge from false membership.
type Membership string

// The four governed outcomes.
const (
	Conformant    Membership = "conformant"
	Nonconformant Membership = "nonconformant"
	Unresolved    Membership = "unresolved"
	Unsupported   Membership = "unsupported"
)

var (
	triplet = regexp.MustCompile(`^(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){2}$`)
	debian  = regexp.MustCompile(`^(?:[0-9]+:)?[0-9][A-Za-z0-9.+~]*(?:-[A-Za-z0-9.+~\-]*[A-Za-z0-9.+~])?$`)
	rpmText = regexp.MustCompile("^(?:[0-9]+:)?[A-Za-z0-9][A-Za-z0-9.+_~^]*(?:-[A-Za-z0-9.+_~^]+)?$")
)

// Installed returns a fixed relation identity. No input selects a callback.
func Installed(name string) (Relation, error) {
	if pattern(name) == nil {
		return Relation{}, ErrInput
	}
	text, err := json.Marshal(map[string]string{"relation": name, "revision": "1"})
	if err != nil {
		return Relation{}, err
	}
	canonical, err := canonjson.JCS(text)
	if err != nil {
		return Relation{}, err
	}
	return Relation{
		Authority: "https://openrae.org/semantics/versions",
		ID:        name, Revision: "1", Digest: digest.SHA256(canonical),
	}, nil
}

// Domain is an immutable, optional one-sided or bounded version restriction.
type Domain struct {
	relation                 Relation
	lower, upper             string
	hasLower, hasUpper       bool
	lowerClosed, upperClosed bool
}

// NewDomain validates and copies the endpoints. Unsupported relation identities
// are preserved, but their membership is Unsupported.
func NewDomain(relation Relation, lower, upper *string, lowerClosed, upperClosed bool) (Domain, error) {
	d := Domain{relation: relation, lowerClosed: lowerClosed, upperClosed: upperClosed}
	if lower == nil && upper == nil {
		return Domain{}, ErrInput
	}
	if lower != nil {
		d.lower, d.hasLower = *lower, true
	}
	if upper != nil {
		d.upper, d.hasUpper = *upper, true
	}
	if !d.validBounds() {
		return Domain{}, ErrInput
	}
	return d, nil
}

func (d Domain) installed() bool {
	identity, err := Installed(d.relation.ID)
	return err == nil && identity == d.relation
}

// Validate checks the domain, including the otherwise unrestricted zero value.
func (d Domain) Validate() error {
	if !d.hasLower && !d.hasUpper || !d.validBounds() {
		return ErrInput
	}
	return nil
}

func (d Domain) validBounds() bool {
	for _, bound := range []struct {
		text string
		set  bool
	}{{d.lower, d.hasLower}, {d.upper, d.hasUpper}} {
		if bound.set && (bound.text == "" || !utf8.ValidString(bound.text) || utf8.RuneCountInString(bound.text) > 256) {
			return false
		}
		if bound.set && d.installed() && !pattern(d.relation.ID).MatchString(bound.text) {
			return false
		}
	}
	if !d.installed() || !d.hasLower || !d.hasUpper {
		return true
	}
	ordering := compare(d.relation.ID, d.lower, d.upper)
	return ordering < 0 || ordering == 0 && d.lowerClosed && d.upperClosed
}

// Membership evaluates one value without collapsing unsupported or unresolved
// states into false. Construction is required; a zero Domain is unsupported.
func (d Domain) Membership(value any) Membership {
	if !d.installed() {
		return Unsupported
	}
	text, ok := value.(string)
	if !ok || len(text) > 256 || !pattern(d.relation.ID).MatchString(text) {
		return Unresolved
	}
	if d.hasLower {
		ordering := compare(d.relation.ID, text, d.lower)
		if ordering < 0 || ordering == 0 && !d.lowerClosed {
			return Nonconformant
		}
	}
	if d.hasUpper {
		ordering := compare(d.relation.ID, text, d.upper)
		if ordering > 0 || ordering == 0 && !d.upperClosed {
			return Nonconformant
		}
	}
	return Conformant
}

func pattern(name string) *regexp.Regexp {
	switch name {
	case "numeric-triplet":
		return triplet
	case "debian":
		return debian
	case "rpm":
		return rpmText
	default:
		return nil
	}
}

func compare(relation, left, right string) int {
	if relation == "numeric-triplet" {
		return slices.Compare(tripletParts(left), tripletParts(right))
	}
	firstEpoch, first := epoch(left)
	secondEpoch, second := epoch(right)
	if order := firstEpoch.Cmp(secondEpoch); order != 0 {
		return order
	}
	if relation == "rpm" {
		return rpm.NewVersion(first).Compare(rpm.NewVersion(second))
	}
	firstVersion, firstRevision := debianParts(first)
	secondVersion, secondRevision := debianParts(second)
	if order := debianCompare(firstVersion, secondVersion); order != 0 {
		return order
	}
	return debianCompare(firstRevision, secondRevision)
}

func tripletParts(text string) []int {
	parts := strings.Split(text, ".")
	values := make([]int, len(parts))
	for i, part := range parts {
		values[i], _ = strconv.Atoi(part) // Validated, at most nine digits.
	}
	return values
}

func epoch(text string) (*big.Int, string) {
	if value, rest, found := strings.Cut(text, ":"); found {
		parsed, _ := new(big.Int).SetString(value, 10)
		return parsed, rest
	}
	return new(big.Int), text
}

func debianParts(text string) (version, revision string) {
	if version, revision, found := strings.CutLast(text, "-"); found {
		return version, revision
	}
	return text, "0"
}

// debianCompare follows Debian Policy 5.6.12: alternate non-digit lexical
// comparison and exact numeric digit-run comparison. No digit run is narrowed.
func debianCompare(left, right string) int {
	for left != "" || right != "" {
		for nonDigit(left) || nonDigit(right) {
			if order := cmp.Compare(debianOrder(head(left)), debianOrder(head(right))); order != 0 {
				return order
			}
			left, right = tail(left), tail(right)
		}
		first, restLeft := digits(left)
		second, restRight := digits(right)
		first, second = strings.TrimLeft(first, "0"), strings.TrimLeft(second, "0")
		if order := cmp.Compare(len(first), len(second)); order != 0 {
			return order
		}
		if order := strings.Compare(first, second); order != 0 {
			return order
		}
		left, right = restLeft, restRight
	}
	return 0
}

func head(text string) byte {
	if text == "" {
		return 0
	}
	return text[0]
}

func tail(text string) string {
	if text == "" {
		return ""
	}
	return text[1:]
}

func nonDigit(text string) bool {
	return text != "" && (text[0] < '0' || text[0] > '9')
}

func digits(text string) (prefix, rest string) {
	i := 0
	for i < len(text) && text[i] >= '0' && text[i] <= '9' {
		i++
	}
	return text[:i], text[i:]
}

func debianOrder(ch byte) int {
	if ch == '~' {
		return -1
	}
	if ch == 0 || ch >= '0' && ch <= '9' {
		return 0
	}
	if ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' {
		return int(ch)
	}
	return int(ch) + 256
}
