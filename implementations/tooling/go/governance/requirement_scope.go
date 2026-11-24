package governance

import (
	"context"
	"encoding/json"
	"errors"
	"io/fs"
	"path"
	"regexp"
	"slices"
	"strings"
	"time"
)

const scopeLimit = 256 * 1024
const scopeReadFailure = "Requirement scope cannot be read and validated."

type scopeError string

func (e scopeError) Error() string { return string(e) }

type requirementScope struct {
	issue    string
	primary  string
	uids     []string
	bindings map[string][]string
}

func scopeUIDs(value any) ([]string, error) {
	uids, valid := stringList(value, false)
	if !valid || len(uids) < 1 || len(uids) > 64 {
		return nil, scopeError("Scope requires a nonempty unique list of canonical requirement UIDs.")
	}
	seen := map[string]bool{}
	for _, uid := range uids {
		if !canonicalUID(uid) || seen[uid] {
			return nil, scopeError("Scope requires a nonempty unique list of canonical requirement UIDs.")
		}
		seen[uid] = true
	}
	return uids, nil
}

func exactScopePath(value any) bool {
	name, ok := value.(string)
	if !ok || name == "" || strings.ContainsAny(name, `\:*?[]`) || strings.HasPrefix(name, "/") || path.Clean(name) != name || secretPath(name) {
		return false
	}
	for part := range strings.SplitSeq(name, "/") {
		if part == "." || part == ".." {
			return false
		}
	}
	for _, r := range name {
		if r < 32 || r == 127 {
			return false
		}
	}
	return true
}

func parseRequirementScope(value any, issue string) (*requirementScope, error) {
	m, ok := value.(*mapping)
	fields := []string{"schema_version", "issue_number", "primary_requirement_uid", "requirement_uids", "bindings"}
	if !ok || m.size() != len(fields) {
		return nil, scopeError("Scope must contain exactly the supported fields.")
	}
	for _, field := range fields {
		if !m.has(field) {
			return nil, scopeError("Scope must contain exactly the supported fields.")
		}
	}
	number, integer := m.get("issue_number").(json.Number)
	if m.get("schema_version") != "requirement-scope/v1" || !integer || string(number) != issue || issue == "0" {
		return nil, scopeError("Scope version or issue identity does not match its canonical location.")
	}
	uids, err := scopeUIDs(m.get("requirement_uids"))
	if err != nil {
		return nil, err
	}
	primary, ok := m.get("primary_requirement_uid").(string)
	if !ok || !slices.Contains(uids, primary) {
		return nil, scopeError("The primary requirement must be explicitly in scope.")
	}
	bindings, err := scopeBindings(m.get("bindings"), uids)
	if err != nil {
		return nil, err
	}
	return &requirementScope{issue: issue, primary: primary, uids: uids, bindings: bindings}, nil
}

func scopeBindings(value any, uids []string) (map[string][]string, error) {
	m, ok := value.(*mapping)
	if !ok || m.size() == 0 {
		return nil, scopeError("Scope requires exact file assignments.")
	}
	bindings := map[string][]string{}
	for _, key := range m.keys {
		if !exactScopePath(key) {
			return nil, scopeError("Scope assignments must name canonical repository-relative files.")
		}
		owners, err := scopeUIDs(m.get(key))
		if err != nil {
			return nil, err
		}
		for _, owner := range owners {
			if !slices.Contains(uids, owner) {
				return nil, scopeError("A file assignment names a requirement outside the declared scope.")
			}
		}
		name, ok := key.(string)
		if !ok {
			return nil, scopeError("Scope assignments must name canonical repository-relative files.")
		}
		bindings[name] = owners
	}
	return bindings, nil
}

func loadRequirementScope(ctx context.Context, r *repository, branch string) (*requirementScope, error) {
	match := regexp.MustCompile(`^([1-9][0-9]*)-[A-Za-z0-9][A-Za-z0-9._/-]*$`).FindStringSubmatch(branch)
	if match == nil {
		return nil, nil //nolint:nilnil // An undeclared optional scope is a valid absence.
	}
	if len(match[1]) > 4300 {
		return nil, scopeError(scopeReadFailure)
	}
	name := "docs/governance/requirement-scopes/" + match[1] + ".json"
	resolved, err := r.resolve(name)
	if err != nil || resolved != name {
		return nil, scopeError(scopeReadFailure)
	}
	info, err := r.root.Stat(name)
	if errors.Is(err, fs.ErrNotExist) {
		established, historyErr := scopeEstablished(ctx, r, name)
		if historyErr != nil || established {
			return nil, scopeError(scopeReadFailure)
		}
		return nil, nil //nolint:nilnil // An undeclared optional scope is a valid absence.
	}
	if err != nil || !info.Mode().IsRegular() || info.Size() > scopeLimit {
		return nil, scopeError(scopeReadFailure)
	}
	data, err := r.read(name)
	if err != nil {
		return nil, scopeError(scopeReadFailure)
	}
	value, err := decodeJSON(data, scopeLimit, true)
	if err != nil {
		return nil, scopeError(scopeReadFailure)
	}
	scope, err := parseRequirementScope(value, match[1])
	if err != nil {
		return nil, scopeError(scopeReadFailure)
	}
	return scope, nil
}

func scopeEstablished(ctx context.Context, r *repository, name string) (bool, error) {
	if _, err := r.root.Stat(".git"); errors.Is(err, fs.ErrNotExist) {
		return false, nil
	}
	commands := [][]string{{"log", "--all", "--full-history", "-1", "--format=%H", "--", name}, {"ls-files", "--", name}}
	established := false
	for _, args := range commands {
		bounded, cancel := context.WithTimeout(ctx, 10*time.Second)
		data, err := r.git(bounded, "", args...)
		cancel()
		if err != nil {
			return false, err
		}
		if strings.TrimSpace(string(data)) != "" {
			established = true
		}
	}
	return established, nil
}
