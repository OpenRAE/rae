package processor_test

import (
	"encoding/json"
	"os"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestParticipantSourceGuardsMatchDirectReferenceTests(t *testing.T) {
	raw, err := os.ReadFile("testdata/participant-source-guards.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []struct {
		Name     string `json:"name"`
		Source   string `json:"source"`
		Accepted bool   `json:"accepted"`
	}
	if checkErr := json.Unmarshal(raw, &cases); checkErr != nil {
		t.Fatal(checkErr)
	}
	if len(cases) != 13 {
		t.Fatal("participant authored guard inventory changed")
	}
	for _, test := range cases {
		t.Run(test.Name, func(t *testing.T) {
			_, err := sdl.Parse([]byte(test.Source), sdl.DefaultParseOptions())
			if (err == nil) != test.Accepted {
				t.Fatalf("accepted=%v err=%v", test.Accepted, err)
			}
		})
	}
}
