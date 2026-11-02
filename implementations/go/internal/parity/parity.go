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
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"regexp"
	"strings"
)

// Schema is the schema identifier of the corpus manifest.
const Schema = "raes-parity-corpus/v2"

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
	if err := validateManifest(fsys); err != nil {
		return nil, err
	}
	var cases []Case
	seen := map[string]bool{}
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
		identity := c.Key() + "/" + c.Name
		if seen[identity] {
			return fmt.Errorf("%s: duplicate case %q", name, identity)
		}
		seen[identity] = true
		cases = append(cases, c)
		return nil
	})
	if err != nil {
		return nil, err
	}
	if len(cases) == 0 {
		return nil, errors.New("corpus contains no cases")
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
	if strings.TrimSpace(record.Name) == "" || strings.TrimSpace(record.Surface) == "" || strings.TrimSpace(record.Command) == "" {
		return Case{}, fmt.Errorf("%s: missing case identity", name)
	}
	if len(record.Result) == 0 || bytes.Equal(record.Result, []byte("null")) {
		return Case{}, fmt.Errorf("%s: missing result", name)
	}
	files := make(map[string][]byte, len(record.Files))
	for fileName, digest := range record.Files {
		if !fs.ValidPath(fileName) || strings.Contains(fileName, "\\") || strings.Contains(fileName, ":") {
			return Case{}, fmt.Errorf("%s: unsafe input name %q", name, fileName)
		}
		if !hexDigest(digest, 64) {
			return Case{}, fmt.Errorf("%s: invalid input digest", name)
		}
		content, err := readBlob(fsys, digest)
		if err != nil {
			return Case{}, fmt.Errorf("%s: input %s: %w", name, fileName, err)
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
	content, err := documentBytes(fsys, name)
	if err != nil {
		return err
	}
	return decodeJSON(content, name, v)
}

func decodeJSON(content []byte, name string, v any) error {
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

// hexDigest accepts only a lowercase hexadecimal digest of the given length.
func hexDigest(value string, length int) bool {
	if len(value) != length {
		return false
	}
	for _, digit := range value {
		if (digit < '0' || digit > '9') && (digit < 'a' || digit > 'f') {
			return false
		}
	}
	return true
}

func validateManifest(fsys fs.FS) error {
	var manifest struct {
		Schema     string `json:"schema"`
		Provenance struct {
			PythonCommit   string `json:"python_commit"`
			PythonTree     string `json:"python_tree"`
			RecorderSHA256 string `json:"recorder_sha256"`
			PythonVersion  string `json:"python_version"`
			LockSHA256     string `json:"lock_sha256"`
		} `json:"provenance"`
	}
	if err := decodeFile(fsys, "manifest.json", &manifest); err != nil {
		return err
	}
	if manifest.Schema != Schema {
		return fmt.Errorf("manifest.json: schema is %q, want %q", manifest.Schema, Schema)
	}
	for name, value := range map[string]string{
		"python_commit": manifest.Provenance.PythonCommit,
		"python_tree":   manifest.Provenance.PythonTree,
	} {
		if !hexDigest(value, 40) {
			return fmt.Errorf("manifest.json: invalid %s", name)
		}
	}
	for name, value := range map[string]string{
		"recorder_sha256": manifest.Provenance.RecorderSHA256,
		"lock_sha256":     manifest.Provenance.LockSHA256,
	} {
		if !hexDigest(value, 64) {
			return fmt.Errorf("manifest.json: invalid %s", name)
		}
	}
	if !regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+$`).MatchString(manifest.Provenance.PythonVersion) {
		return errors.New("manifest.json: invalid python_version")
	}
	return nil
}
