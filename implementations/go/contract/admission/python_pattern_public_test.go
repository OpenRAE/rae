package admission

import (
	"encoding/json"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestPythonPatternSyntaxPublicVerdicts(t *testing.T) {
	for _, fixture := range []struct {
		file  string
		count int
	}{{"testdata/metadata-regex-verdicts.json", 130}, {"testdata/cpython-pattern-verdicts.json", 347}} {
		t.Run(fixture.file, func(t *testing.T) { checkPublicPatternCases(t, fixture.file, fixture.count) })
	}
}

func checkPublicPatternCases(t *testing.T, file string, count int) {
	t.Helper()
	raw, err := os.ReadFile(file) // #nosec G304 -- Callers select fixed reference fixtures in this package.
	if err != nil {
		t.Fatal(err)
	}
	var recorded struct {
		Cases []struct {
			Pattern string `json:"pattern"`
			Valid   bool   `json:"valid"`
		} `json:"cases"`
	}
	if err := json.Unmarshal(raw, &recorded); err != nil {
		t.Fatal(err)
	}
	if len(recorded.Cases) != count {
		t.Fatal("recorded syntax inventory changed")
	}
	for i, tc := range recorded.Cases {
		t.Run(strconv.Itoa(i), func(t *testing.T) {
			_, err := ParsePythonPattern(tc.Pattern)
			if (err == nil) != tc.Valid {
				t.Fatalf("public syntax accepted=%t, want %t", err == nil, tc.Valid)
			}
		})
	}
}

func TestPythonPatternNamedCharacterOwnership(t *testing.T) {
	parsed, err := ParsePythonPattern(`\N{LATIN CAPITAL LETTER G}\N{LF}`)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name string
		want rune
	}{{"LATIN CAPITAL LETTER G", 'G'}, {"latin capital letter g", 'G'}, {"LF", '\n'}} {
		if got, ok := parsed.NamedCharacter(tc.name); !ok || got != tc.want {
			t.Errorf("named character=%U known=%t, want %U", got, ok, tc.want)
		}
	}
	if _, ok := parsed.NamedCharacter("LATIN CAPITAL LETTER H"); ok {
		t.Fatal("result exposes a name absent from its expression")
	}
	other, err := ParsePythonPattern("GOV-001")
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := other.NamedCharacter("LF"); ok {
		t.Fatal("another expression borrowed named facts")
	}
	var zero PythonPatternSyntax
	if _, ok := zero.NamedCharacter("LF"); ok {
		t.Fatal("zero value provides named facts")
	}
}

func TestPythonPatternSyntaxErrorContract(t *testing.T) {
	if _, err := ParsePythonPattern("GOV-001"); err != nil {
		t.Fatal(err)
	}
	const source = "not-a-valid-pattern("
	_, err := ParsePythonPattern(source)
	if err == nil {
		t.Fatal("malformed pattern was accepted")
	}
	if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
		t.Fatalf("error category=%v known=%t", category, ok)
	}
	if strings.Contains(err.Error(), source) {
		t.Fatal("error includes caller pattern text")
	}
}

func TestPythonPatternSharedParser(t *testing.T) {
	for _, source := range []string{"", `(?i)(?m)^gov-001`, `(?<=ab|cd)x`, `(?<!G+)GOV-001`, `(?P<1>GOV)-001`, `\N{LATIN CAPITAL LETTER G}OV-001`} {
		_, err := ParsePythonPattern(source)
		if (err == nil) != pythonPatternValid(source) {
			t.Fatal("public and model syntax paths disagree")
		}
	}
}
