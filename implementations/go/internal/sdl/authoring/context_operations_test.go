package authoring

import (
	"context"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func TestCompositionHonorsCallerCancellation(t *testing.T) {
	parser := operationParser(t)
	ctx, cancel := context.WithCancel(t.Context())
	cancel()
	request := Request{Source: []byte("name: canceled\n"), Name: "main.yaml", FS: forbiddenFS{}}
	checks := map[string]func() error{
		"decode": func() error { _, err := parser.DecodeContext(ctx, request); return err },
		"format": func() error { _, err := parser.FormatContext(ctx, request); return err },
	}
	for name, check := range checks {
		t.Run(name, func(t *testing.T) {
			category, known := fault.CategoryOf(check())
			if !known || category != fault.Operational {
				t.Fatal("canceled operation lost its operational refusal")
			}
		})
	}
}
