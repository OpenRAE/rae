package parity

import "testing"

func TestSDLOperationCommands(t *testing.T) {
	cases, err := loadTestCases()
	if err != nil {
		t.Fatal(err)
	}
	registry := runners()
	for _, key := range []string{"cli sdl resolve", "cli sdl verify-imports", "cli sdl publish", "cli semantic resolve", "cli semantic normalize", "cli semantic transform"} {
		t.Run(key, func(t *testing.T) {
			run, present := registry[key]
			if !present {
				t.Fatalf("missing native runner for %s", key)
			}
			selected := []Case{}
			for _, c := range cases {
				if c.Key() == key {
					selected = append(selected, c)
				}
			}
			if len(selected) == 0 {
				t.Fatal("no scoped reference cases")
			}
			checkCases(t, run, selected)
		})
	}
}
