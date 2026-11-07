package parity

import (
	"context"
	"encoding/json"
	"errors"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/authoring"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// formatRunner shares the immutable model owner; every request gets isolated
// input files and composition state. The corpus adapter grants no host access.
func formatRunner() Runner {
	parser, loadErr := authoring.New(source.DefaultLimits())
	return func(_ context.Context, c Case) (json.RawMessage, error) {
		if loadErr != nil {
			return nil, loadErr
		}
		if len(c.Args) < 3 {
			return nil, errors.New("format runner: missing source path")
		}
		name := c.Args[2]
		raw, ok := c.Files[name]
		if !ok {
			return nil, errors.New("format runner: missing source")
		}
		files := fstest.MapFS{}
		for path, content := range c.Files {
			files[path] = &fstest.MapFile{Data: content}
		}
		result, err := parser.Format(authoring.Request{Source: raw, Name: name, FS: files})
		if err != nil {
			return json.Marshal(map[string]any{"exit_code": 1, "stdout": nil})
		}
		options := source.DefaultOptions()
		options.KeyScope = "data"
		document, err := source.Decode(result.Content, options)
		if err != nil {
			return nil, err
		}
		return json.Marshal(map[string]any{"exit_code": 0, "stdout": document.Value()})
	}
}
