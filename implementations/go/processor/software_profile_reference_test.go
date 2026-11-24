package processor_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestCompiledSoftwareProfilesKeepReferenceAuthority(t *testing.T) {
	raw, err := os.ReadFile("testdata/software-profile-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name      string          `json:"name"`
		Source    json.RawMessage `json:"source"`
		Authority json.RawMessage `json:"authority"`
		Refused   bool            `json:"refused"`
	}
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			scenario, err := sdl.Parse(test.Source, sdl.DefaultParseOptions())
			if err != nil {
				t.Fatal(err)
			}
			compiled, err := processor.Compile(scenario, nil)
			if test.Refused {
				assertUnresolvedSoftwareAuthorityRefusal(t, err)
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			assertReferenceJSON(t, "software profile authority", requireJSON(t, compiled.Model().View().ProfileAuthority), test.Authority)
		})
	}
}

func assertUnresolvedSoftwareAuthorityRefusal(t *testing.T, err error) {
	t.Helper()
	if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
		t.Fatalf("unresolved software authority error=%v", err)
	}
}
