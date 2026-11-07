package parity

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
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
		command, valid := formatArguments(c.Args)
		if !valid {
			return formatEnvelope(2, nil)
		}
		raw, present := c.Files[command.name]
		if !present {
			return nil, errors.New("format runner: missing source")
		}
		// The reference CLI reads text with universal newline conversion.
		original := bytes.ReplaceAll(bytes.ReplaceAll(raw, []byte("\r\n"), []byte("\n")), []byte("\r"), []byte("\n"))
		files := fstest.MapFS{}
		for name, content := range c.Files {
			files[name] = &fstest.MapFile{Data: content}
		}
		result, err := parser.Format(authoring.Request{Source: original, Name: command.name, FS: files})
		if err != nil {
			return formatRefusal(err)
		}
		return formattedEnvelope(command, original, result.Content)
	}
}
func formattedEnvelope(command formatCommand, original, content []byte) (json.RawMessage, error) {
	if command.check {
		if !bytes.Equal(original, content) {
			return formatEnvelope(1, nil)
		}
		return formatEnvelope(0, nil)
	}
	if command.write {
		return formatEnvelope(0, nil)
	}
	options := source.DefaultOptions()
	options.KeyScope = "data"
	document, err := source.Decode(content, options)
	if err != nil {
		return nil, err
	}
	return formatEnvelope(0, document.Value())
}
func formatRefusal(err error) (json.RawMessage, error) {
	classified, hasCode := errors.AsType[interface {
		error
		Code() string
	}](err)
	if hasCode && classified.Code() == "sdl-semantic-invalid" {
		return formatEnvelope(1, nil)
	}
	category, known := fault.CategoryOf(err)
	if known && category == fault.InvalidInput || hasCode && strings.HasPrefix(classified.Code(), "sdl.import.") {
		return formatEnvelope(2, nil)
	}
	return nil, err
}
func formatEnvelope(code int, stdout any) (json.RawMessage, error) {
	return json.Marshal(map[string]any{"exit_code": code, "stdout": stdout})
}

type formatCommand struct {
	name                  string
	check, write, literal bool
}

func formatArguments(args []string) (formatCommand, bool) {
	var command formatCommand
	if len(args) < 3 || args[0] != "sdl" || args[1] != "format" {
		return command, false
	}
	for _, arg := range args[2:] {
		if !command.take(arg) {
			return command, false
		}
	}
	return command, command.name != "" && (!command.check || !command.write)
}
func (c *formatCommand) take(arg string) bool {
	if !c.literal {
		switch arg {
		case "--":
			c.literal = true
			return true
		case "--check":
			c.check = true
			return true
		case "--write":
			c.write = true
			return true
		default:
			if len(arg) > 1 && strings.HasPrefix(arg, "-") {
				return false
			}
		}
	}
	if c.name != "" {
		return false
	}
	c.name = arg
	return true
}
