// Package parity checks the Go implementation against the golden corpus that
// the Python implementation recorded (issue #1778).
//
// The corpus is in testdata. manifest.json names the corpus schema. Each file
// under cases/ records one invocation of a surface command: its name, its
// surface, its command, its arguments, its input files by SHA-256 digest, and
// its result. inputs/ holds each input file once, under its digest.
// tools/parity_corpus.py records the corpus and documents the surfaces and
// their results.
//
// Each Go port adds a [Runner] for the commands that it implements to the
// registry in runners.go. TestCorpus runs each case that has a runner, and it
// skips and so reports each command that has no runner yet.
package parity

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"path"
)

// Schema is the schema identifier of the corpus manifest.
const Schema = "raes-parity-corpus/v1"

// Case is one recorded invocation of a surface command.
type Case struct {
	// Name identifies the case. It follows the path of the recorded input.
	Name    string
	Surface string
	Command string
	Args    []string
	// Files maps the name of each input file to its content.
	Files map[string][]byte
	// Result is the recorded result in its JSON form.
	Result json.RawMessage
}

// Key returns the registry key of the case: its surface and its command.
func (c Case) Key() string {
	return c.Surface + " " + c.Command
}

// Runner runs a case and returns its result in the recorded JSON form.
type Runner func(ctx context.Context, c Case) (json.RawMessage, error)

// Load returns the cases of the corpus in fsys. It rejects an unknown schema,
// unknown fields, and an input file whose content does not match its digest.
func Load(fsys fs.FS) ([]Case, error) {
	var manifest struct {
		Schema    string `json:"schema"`
		Reference struct {
			Source      string `json:"source_sha256"`
			Recorder    string `json:"recorder_sha256"`
			Environment string `json:"environment_sha256"`
			Python      string `json:"python_version"`
			Interpreter string `json:"python"`
			Unicode     string `json:"unicode"`
		} `json:"reference"`
	}
	if err := decodeFile(fsys, "manifest.json", &manifest); err != nil {
		return nil, err
	}
	if manifest.Schema != Schema {
		return nil, fmt.Errorf("manifest.json: schema is %q, want %q", manifest.Schema, Schema)
	}
	if manifest.Reference.Python == "" || manifest.Reference.Interpreter == "" || manifest.Reference.Unicode == "" {
		return nil, errors.New("manifest.json: missing Python version")
	}
	for _, digest := range []string{manifest.Reference.Source, manifest.Reference.Recorder, manifest.Reference.Environment} {
		if !validDigest(digest) {
			return nil, errors.New("manifest.json: missing or invalid reference identity")
		}
	}
	var cases []Case
	err := fs.WalkDir(fsys, "cases", func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		c, err := loadCase(fsys, name)
		if err != nil {
			return err
		}
		cases = append(cases, c)
		return nil
	})
	if err != nil {
		return nil, err
	}
	return cases, nil
}

func loadCase(fsys fs.FS, name string) (Case, error) {
	var record struct {
		Name    string            `json:"name"`
		Surface string            `json:"surface"`
		Command string            `json:"command"`
		Args    []string          `json:"args"`
		Files   map[string]string `json:"files"`
		Result  json.RawMessage   `json:"result"`
	}
	if err := decodeFile(fsys, name, &record); err != nil {
		return Case{}, err
	}
	files := make(map[string][]byte, len(record.Files))
	for fileName, digest := range record.Files {
		if !validDigest(digest) {
			return Case{}, fmt.Errorf("%s: input %s has an invalid digest", name, fileName)
		}
		content, err := fs.ReadFile(fsys, path.Join("inputs", digest))
		if err != nil {
			return Case{}, fmt.Errorf("%s: input %s: %w", name, fileName, err)
		}
		if sum := sha256.Sum256(content); hex.EncodeToString(sum[:]) != digest {
			return Case{}, fmt.Errorf("%s: input %s does not match its digest", name, fileName)
		}
		files[fileName] = content
	}
	return Case{
		Name:    record.Name,
		Surface: record.Surface,
		Command: record.Command,
		Args:    record.Args,
		Files:   files,
		Result:  record.Result,
	}, nil
}

// decodeFile decodes the single JSON value in the file name into v.
func decodeFile(fsys fs.FS, name string, v any) error {
	content, err := fs.ReadFile(fsys, name)
	if err != nil {
		return err
	}
	decoder := json.NewDecoder(bytes.NewReader(content))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return fmt.Errorf("decode %s: %w", name, err)
	}
	if _, err := decoder.Token(); !errors.Is(err, io.EOF) {
		return fmt.Errorf("decode %s: data follows the value", name)
	}
	return nil
}

// validDigest admits only the content-addressed store's lowercase SHA-256 names.
func validDigest(digest string) bool {
	if len(digest) != sha256.Size*2 {
		return false
	}
	for _, ch := range digest {
		if (ch < '0' || ch > '9') && (ch < 'a' || ch > 'f') {
			return false
		}
	}
	return true
}
