package governance

import (
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"syscall"
	"unicode/utf8"
)

var errUnsafePath = errors.New("repository path is unsafe")
var errNotUTF8 = errors.New("repository source is not UTF-8")

type repository struct {
	root     *os.Root
	dir      string
	absolute string
}

func validRevision(value string) bool {
	return regexp.MustCompile(`^[A-Za-z0-9_][A-Za-z0-9_./@^~{}-]*$`).MatchString(value)
}

func openRepository(dir string) (*repository, error) {
	if dir == "" {
		dir = "."
	}
	if secretPath(dir) {
		return nil, errUnsafePath
	}
	absolute, err := absoluteReferencePath(dir)
	if err != nil {
		return nil, err
	}
	absolute, err = repositoryDirectory(absolute)
	if err != nil {
		return nil, err
	}
	if secretPath(absolute) {
		return nil, errUnsafePath
	}
	root, err := os.OpenRoot(absolute)
	if err != nil {
		return nil, err
	}
	return &repository{root: root, dir: absolute, absolute: absolute}, nil
}

func absoluteReferencePath(name string) (string, error) {
	if filepath.IsAbs(name) {
		return name, nil
	}
	cwd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	return cwd + string(filepath.Separator) + name, nil
}

func repositoryDirectory(absolute string) (string, error) {
	if secretPath(absolute) {
		return "", errUnsafePath
	}
	volume := filepath.VolumeName(absolute) + string(filepath.Separator)
	root, err := os.OpenRoot(volume)
	if err != nil {
		return "", err
	}
	defer func() { _ = root.Close() }()
	r := repository{root: root, absolute: volume}
	relative := strings.TrimPrefix(absolute, volume)
	resolved, err := r.resolveLinks(relative, map[string]bool{})
	if err != nil {
		return "", err
	}
	return filepath.Join(volume, resolved), nil
}

func secretPath(name string) bool {
	return slices.Contains(strings.Split(filepath.ToSlash(name), "/"), ".secrets")
}

func repositoryPath(name string) bool {
	if filepath.IsAbs(name) || strings.ContainsRune(name, 0) || secretPath(name) {
		return false
	}
	return !slices.Contains(strings.Split(filepath.ToSlash(name), "/"), "..")
}

func (r *repository) safe(name string) bool {
	_, err := r.resolve(name)
	return err == nil
}

// Resolve link text through Root before opening a file. Absolute links to a
// contained target are valid in the reference profile. Only the normalized,
// contained target is passed back to Root, so a subsequent link substitution
// remains subject to Root's own escape checks.
func (r *repository) resolve(name string) (string, error) {
	if !repositoryPath(name) {
		return "", errUnsafePath
	}
	return r.resolveLinks(filepath.Clean(name), map[string]bool{})
}

func (r *repository) resolveLinks(name string, active map[string]bool) (string, error) {
	return r.resolveLinkProfile(name, active, false)
}

func (r *repository) resolveLinkProfile(name string, active map[string]bool, directories bool) (string, error) {
	resolved := "."
	for part := range strings.SplitSeq(filepath.ToSlash(name), "/") {
		next, err := r.resolvePart(resolved, part, active, directories)
		if err != nil {
			return "", err
		}
		resolved = next
	}
	return resolved, nil
}

func (r *repository) resolvePart(resolved, part string, active map[string]bool, directories bool) (string, error) {
	if part == ".." {
		if resolved == "." {
			if r.absolute == filepath.VolumeName(r.absolute)+string(filepath.Separator) {
				return ".", nil // A filesystem volume has no parent outside itself.
			}
			return "", errUnsafePath
		}
		return filepath.Dir(resolved), nil
	}
	candidate := filepath.Join(resolved, part)
	if secretPath(candidate) {
		return "", errUnsafePath
	}
	info, err := r.root.Lstat(candidate)
	if !directories && (errors.Is(err, fs.ErrNotExist) || errors.Is(err, syscall.ENOTDIR)) {
		return candidate, nil // Non-strict resolution retains missing components, including a later parent step.
	}
	if err != nil {
		return "", err
	}
	if info.Mode()&os.ModeSymlink == 0 {
		if directories && !info.IsDir() {
			return "", &fs.PathError{Op: "resolve", Path: candidate, Err: syscall.ENOTDIR}
		}
		return candidate, nil
	}
	return r.followLink(candidate, active, directories)
}

func (r *repository) read(name string) ([]byte, error) {
	resolved, err := r.resolve(name)
	if err != nil {
		return nil, err
	}
	return r.root.ReadFile(resolved)
}

func (r *repository) readLimit(name string, limit int64) ([]byte, error) {
	resolved, err := r.resolve(name)
	if err != nil {
		return nil, err
	}
	file, err := r.root.Open(resolved)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	data, err := io.ReadAll(io.LimitReader(file, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > limit {
		return nil, errors.New("repository artifact exceeds its byte limit")
	}
	return data, nil
}

func (r *repository) text(name string) (string, error) {
	data, err := r.read(name)
	if err != nil {
		return "", err
	}
	if !utf8.Valid(data) {
		return "", errNotUTF8
	}
	// Python text reads use universal newlines.
	return strings.ReplaceAll(strings.ReplaceAll(string(data), "\r\n", "\n"), "\r", "\n"), nil
}

func (r *repository) file(name string) bool {
	resolved, err := r.resolve(name)
	if err != nil {
		return false
	}
	info, err := r.root.Stat(resolved)
	return err == nil && info.Mode().IsRegular()
}

func (r *repository) git(ctx context.Context, input string, args ...string) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "git", args...) // #nosec G204 -- The executable is fixed; private callers validate revisions and construct Git argument arrays.
	cmd.Dir = r.dir
	if input != "" {
		cmd.Stdin = strings.NewReader(input)
	}
	return cmd.Output()
}

func (r *repository) changed(ctx context.Context, request Request) ([]string, error) {
	if request.Paths != nil {
		return request.Paths, nil
	}
	args := []string{"diff", "--name-only", "--diff-filter=d"}
	switch {
	case request.Staged:
		args = append(args, "--cached")
	case request.BaseRevision != "":
		if !validRevision(request.BaseRevision) {
			return nil, errors.New("invalid Git base revision")
		}
		args = append(args, request.BaseRevision, "HEAD")
	default:
		args = append(args, "HEAD")
	}
	data, err := r.git(ctx, "", args...)
	if err != nil {
		return nil, err
	}
	if !utf8.Valid(data) {
		return nil, errNotUTF8
	}
	paths := []string{}
	for _, line := range pythonLines(string(data), false) {
		if name := strings.TrimFunc(line, pythonWhitespace); name != "" {
			paths = append(paths, name)
		}
	}
	return paths, nil
}

func (r *repository) followLink(candidate string, active map[string]bool, directories bool) (string, error) {
	identity := filepath.Join(r.absolute, candidate)
	if active[identity] {
		return "", errUnsafePath
	}
	active[identity] = true
	defer delete(active, identity)
	target, err := r.root.Readlink(candidate)
	if err != nil {
		return "", err
	}
	if secretPath(target) || strings.ContainsRune(target, 0) {
		return "", errUnsafePath
	}
	if !filepath.IsAbs(target) {
		target = filepath.Dir(identity) + string(filepath.Separator) + target
	}
	volume := filepath.VolumeName(target) + string(filepath.Separator)
	if r.absolute == volume {
		return r.resolveLinkProfile(strings.TrimPrefix(target, volume), active, directories)
	}
	root, err := os.OpenRoot(volume)
	if err != nil {
		return "", err
	}
	defer func() { _ = root.Close() }()
	anchor := repository{root: root, absolute: volume}
	resolved, err := anchor.resolveLinkProfile(strings.TrimPrefix(target, volume), active, directories)
	if err != nil {
		return "", err
	}
	target = filepath.Join(volume, resolved)
	if target == r.absolute {
		return ".", nil
	}
	prefix := strings.TrimRight(r.absolute, string(filepath.Separator)) + string(filepath.Separator)
	if !strings.HasPrefix(target, prefix) {
		return "", errUnsafePath
	}
	return strings.TrimPrefix(target, prefix), nil
}

// prefixPath drops empty and dot components while preserving parent components.
func prefixPath(value string) string {
	parts := []string{}
	for part := range strings.SplitSeq(value, "/") {
		if part != "" && part != "." {
			parts = append(parts, part)
		}
	}
	if len(parts) == 0 && !strings.HasPrefix(value, "/") {
		return "."
	}
	return strings.Join(parts, "/")
}
