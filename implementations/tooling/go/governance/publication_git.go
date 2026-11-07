package governance

import (
	"context"
	"errors"
	"os/exec"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// Publication uses subprocess text semantics and distinguishes an empty blob
// from a failed lookup. The ADR adapter has a separate binary-blob profile.
func publicationGitText(ctx context.Context, r *repository, args ...string) (*string, error) {
	data, err := r.git(ctx, "", args...)
	if err != nil {
		if cancelled := ctx.Err(); cancelled != nil {
			return nil, cancelled
		}
		if _, exited := errors.AsType[*exec.ExitError](err); exited {
			return nil, nil //nolint:nilnil // Failed lookups are expected absence; an empty successful blob keeps a non-nil string.
		}
		return nil, fault.New(fault.Operational, "schema-publication-git", err)
	}
	if !utf8.Valid(data) {
		return nil, errNotUTF8
	}
	text := strings.ReplaceAll(strings.ReplaceAll(string(data), "\r\n", "\n"), "\r", "\n")
	return &text, nil
}

func publicationBaseCatalog(ctx context.Context, r *repository, base string) (map[string]*mapping, string, error) {
	text, err := publicationGitText(ctx, r, "show", "--end-of-options", base+":"+publicationManifest)
	if err != nil {
		return nil, "", err
	}
	if text == nil {
		return nil, "base schema publication manifest is missing at " + base, nil
	}
	value, err := decodeJSON([]byte(*text), 0, false)
	if err != nil {
		return nil, "base schema publication manifest at " + base + " is not valid JSON", nil //nolint:nilerr // The reference carries malformed-base detail as a policy finding.
	}
	raw := object(value)
	if raw == nil {
		return nil, "base schema publication manifest at " + base + " must be a JSON object", nil
	}
	if raw.get("schema_version") == "schema-publication-manifest/v2" {
		return publicationBaseRecords(ctx, r, base, raw.get("entries_directory"))
	}
	rows, _ := raw.get("schemas").([]any)
	return publicationEntriesByID(rows), "", nil
}

func publicationBaseRecords(ctx context.Context, r *repository, base string, value any) (map[string]*mapping, string, error) {
	directory, ok := value.(string)
	if !ok {
		return nil, "base schema publication manifest at " + base + " has no entries directory", nil
	}
	text, err := publicationGitText(ctx, r, "ls-tree", "-r", "--name-only", "--end-of-options", base, "--", directory)
	if err != nil {
		return nil, "", err
	}
	if text == nil {
		return nil, "base schema publication records at " + base + " could not be listed", nil
	}
	paths := []string{}
	for _, name := range pythonLines(*text, false) {
		if strings.HasSuffix(name, ".json") {
			paths = append(paths, name)
		}
	}
	slices.Sort(paths)
	rows := []any{}
	for _, name := range paths {
		recordText, readErr := publicationGitText(ctx, r, "show", "--end-of-options", base+":"+name)
		if readErr != nil {
			return nil, "", readErr
		}
		var record any
		if recordText != nil {
			record, _ = decodeJSON([]byte(*recordText), 0, false)
		}
		if object(record) == nil {
			return nil, "base schema publication record at " + base + ":" + name + " is invalid", nil
		}
		rows = append(rows, record)
	}
	return publicationEntriesByID(rows), "", nil
}

func publicationEntriesByID(rows []any) map[string]*mapping {
	entries := map[string]*mapping{}
	for _, row := range rows {
		if raw := object(row); raw != nil {
			if id, ok := raw.get("contract_id").(string); ok {
				entries[id] = raw
			}
		}
	}
	return entries
}
