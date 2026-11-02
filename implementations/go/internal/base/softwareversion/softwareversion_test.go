package softwareversion

import (
	"errors"
	"strings"
	"testing"
)

func TestVersionMembershipMatchesUniversBoundaries(t *testing.T) {
	for _, test := range []struct {
		relation, lower, upper, actual string
		closed                         bool
		want                           Membership
	}{
		{"numeric-triplet", "7.9.0", "", "7.10.0", false, Conformant},
		{"numeric-triplet", "", "7.10.0", "7.9.0", false, Conformant},
		{"numeric-triplet", "7.9.0", "", "7.9.0", false, Nonconformant},
		{"numeric-triplet", "", "7.10.0", "7.10.0", false, Nonconformant},
		{"numeric-triplet", "7.9.0", "", "7.10.0-1", false, Unresolved},
		{"numeric-triplet", "0.0.0", "999999999.999999999.999999999", "1.0.0", true, Conformant},
		{"debian", "1:1.0-2", "", "2:0.1-1", false, Conformant},
		{"debian", "", "1.0-1", "1.0~rc1-1", false, Conformant},
		{"debian", "1.0", "1.0", "1.0-0", true, Conformant},
		{"debian", "9223372036854775808:1", "", "9223372036854775809:0", false, Conformant},
		{"debian", "1.999999999999999999999999999999", "", "1.1000000000000000000000000000000", false, Conformant},
		{"debian", "1.0", "", "1-", true, Unresolved},
		{"debian", "1.0", "", "1::2", true, Unresolved},
		{"debian", "1.0", "", "1.0-💥", true, Unresolved},
		{"debian", "1.0", "", "1.0\n", true, Unresolved},
		{"rpm", "1.0-1", "", "1.0-2", false, Conformant},
		{"rpm", "2.0", "2.0.1", "2.0^20250611", false, Conformant},
		{"rpm", "1.0", "", "1.0~rc1", true, Nonconformant},
		{"rpm", "9223372036854775808:1", "", "9223372036854775809:0", false, Conformant},
	} {
		identity, err := Installed(test.relation)
		if err != nil {
			t.Fatal(err)
		}
		var lower, upper *string
		if test.lower != "" {
			lower = &test.lower
		}
		if test.upper != "" {
			upper = &test.upper
		}
		domain, err := NewDomain(identity, lower, upper, test.closed, test.closed)
		if err != nil || domain.Membership(test.actual) != test.want {
			t.Errorf("Membership(%s, %q) = %s, %v, want %s", test.relation, test.actual, domain.Membership(test.actual), err, test.want)
		}
	}
}

func TestVersionIdentityAndEndpointValidation(t *testing.T) {
	identity, err := Installed("numeric-triplet")
	if err != nil {
		t.Fatal(err)
	}
	lower := "1.0.0"
	for _, changed := range []Relation{
		{Authority: "urn:private", ID: identity.ID, Revision: identity.Revision, Digest: identity.Digest},
		{Authority: identity.Authority, ID: identity.ID, Revision: "2", Digest: identity.Digest},
		{Authority: identity.Authority, ID: identity.ID, Revision: identity.Revision, Digest: "sha256:" + strings.Repeat("0", 64)},
		{Authority: identity.Authority, ID: "private-order", Revision: "1"},
	} {
		domain, domainErr := NewDomain(changed, &lower, nil, true, true)
		if domainErr != nil || domain.Membership("2.0.0") != Unsupported {
			t.Errorf("changed semantic identity = %s, %v, want unsupported", domain.Membership("2.0.0"), domainErr)
		}
	}
}

func TestVersionEndpointValidationAndCopying(t *testing.T) {
	identity, err := Installed("numeric-triplet")
	if err != nil {
		t.Fatal(err)
	}
	lower := "1.0.0"
	for _, bounds := range [][2]string{{"", ""}, {"1.0", ""}, {"2.0.0", "1.0.0"}, {strings.Repeat("a", 257), ""}} {
		var first, second *string
		if bounds[0] != "" {
			first = &bounds[0]
		}
		if bounds[1] != "" {
			second = &bounds[1]
		}
		if _, boundErr := NewDomain(identity, first, second, true, true); !errors.Is(boundErr, ErrInput) {
			t.Errorf("NewDomain(%q) error = %v, want ErrInput", bounds, boundErr)
		}
	}
	if _, singletonErr := NewDomain(identity, &lower, &lower, false, true); !errors.Is(singletonErr, ErrInput) {
		t.Errorf("open singleton error = %v, want ErrInput", singletonErr)
	}
	domain, err := NewDomain(identity, &lower, nil, true, true)
	if err != nil {
		t.Fatal(err)
	}
	lower = "9.0.0"
	if domain.Membership("2.0.0") != Conformant || domain.Membership(2) != Unresolved {
		t.Error("version domain aliased its input or accepted a non-string")
	}
	if err := (Domain{}).Validate(); !errors.Is(err, ErrInput) {
		t.Errorf("zero Domain validation = %v, want ErrInput", err)
	}
	if _, err := Installed("private-order"); !errors.Is(err, ErrInput) {
		t.Errorf("Installed(private) error = %v, want ErrInput", err)
	}
}

func TestUnsupportedBoundsRetainThePublishedCharacterLimit(t *testing.T) {
	identity := Relation{Authority: "urn:private", ID: "private-order", Revision: "1"}
	for _, bound := range []string{strings.Repeat("é", 256), strings.Repeat("a", 256)} {
		domain, err := NewDomain(identity, &bound, nil, true, true)
		if err != nil || domain.Membership("m") != Unsupported {
			t.Errorf("NewDomain(256 characters) = %v, want a preserved unsupported relation", err)
		}
	}
	for _, bound := range []string{"", "\xff", strings.Repeat("é", 257)} {
		if _, err := NewDomain(identity, &bound, nil, true, true); !errors.Is(err, ErrInput) {
			t.Errorf("NewDomain(invalid bound) = %v, want ErrInput", err)
		}
	}
}
