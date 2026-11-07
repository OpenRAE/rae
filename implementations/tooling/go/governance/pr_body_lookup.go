package governance

import (
	"context"
	"io"
	"net/http"
	"os"
	"os/user"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

func prFixtureLookup(name string) (prIssueLookup, error) {
	payload, err := prJSONFile(name, "issues fixture", false)
	if err != nil {
		return nil, err
	}
	return func(_ context.Context, number string) (prIssueFacts, error) {
		value := payload.get(number)
		state, body := value, any("")
		if entry := object(value); entry != nil {
			state = entry.get("state")
			if entry.has("body") {
				body = entry.get("body")
			}
		}
		text, ok := body.(string)
		if !ok {
			return prIssueFacts{}, prLookupError("fixture issue body must be a string")
		}
		return prIssueFacts{state != nil, state == "open", prRequirementUIDs(text)}, nil
	}, nil
}

func prGitHubLookup(repository, token string) (prIssueLookup, error) {
	if !regexp.MustCompile(`^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$`).MatchString(repository) {
		return nil, prConfigurationError("GITHUB_REPOSITORY must have owner/repository form")
	}
	if token == "" {
		return nil, prConfigurationError("GH_TOKEN is required to verify closing issues")
	}
	client := &http.Client{Timeout: 15 * time.Second}
	return func(ctx context.Context, number string) (prIssueFacts, error) {
		return prReadGitHubIssue(ctx, client, "https://api.github.com", repository, token, number)
	}, nil
}

func prReadGitHubIssue(ctx context.Context, client *http.Client, base, repository, token, number string) (prIssueFacts, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, base+"/repos/"+repository+"/issues/"+number, nil)
	if err != nil {
		return prIssueFacts{}, prLookupError("GitHub request could not be constructed")
	}
	request.Header.Set("Accept", "application/vnd.github+json")
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("X-Github-Api-Version", "2022-11-28")
	request.Header.Set("User-Agent", "OpenRAE-pr-body-guard")
	response, err := client.Do(request)
	if err != nil {
		if cancelled := ctx.Err(); cancelled != nil {
			return prIssueFacts{}, cancelled
		}
		return prIssueFacts{}, prLookupError("GitHub request failed")
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode == http.StatusNotFound {
		return prIssueFacts{}, nil
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return prIssueFacts{}, prLookupError("GitHub returned HTTP " + strconv.Itoa(response.StatusCode))
	}
	return prDecodeGitHubIssue(ctx, response.Body)
}

func prDecodeGitHubIssue(ctx context.Context, reader io.Reader) (prIssueFacts, error) {
	data, err := io.ReadAll(reader)
	if err != nil {
		if cancelled := ctx.Err(); cancelled != nil {
			return prIssueFacts{}, cancelled
		}
		return prIssueFacts{}, prLookupError("GitHub response could not be read")
	}
	value, err := decodeJSON(data, 0, false)
	if err != nil {
		return prIssueFacts{}, prLookupError("GitHub returned a malformed issue response")
	}
	payload := object(value)
	if payload == nil || !payload.has("body") {
		return prIssueFacts{}, prLookupError("GitHub returned a malformed issue response")
	}
	body, valid := payload.get("body").(string)
	if payload.get("body") != nil && !valid {
		return prIssueFacts{}, prLookupError("GitHub returned a malformed issue response")
	}
	exists := !payload.has("pull_request")
	return prIssueFacts{exists, exists && payload.get("state") == "open", prRequirementUIDs(body)}, nil
}

func prJSONFile(name, description string, followFinal bool) (*mapping, error) {
	data, err := prExplicitFile(name, description, followFinal)
	if err != nil {
		return nil, prConfigurationError(err.Error())
	}
	text := strings.ReplaceAll(strings.ReplaceAll(string(data), "\r\n", "\n"), "\r", "\n")
	value, err := decodeJSON([]byte(text), 0, false)
	if err != nil {
		return nil, prConfigurationError(description + ": " + err.Error())
	}
	root := object(value)
	if root == nil {
		return nil, prConfigurationError(description + " must be a JSON object")
	}
	return root, nil
}

// Explicit inputs may be outside the repository. Resolve links through Root
// and bind the read to the selected regular inode. The body guard refuses a
// final link; the title guard's ordinary-file profile follows it.
func prExplicitFile(name, description string, followFinal bool) ([]byte, error) {
	r, resolved, err := prExplicitPath(name, description)
	if err != nil {
		return nil, err
	}
	defer func() { _ = r.root.Close() }()
	if followFinal {
		resolved, err = r.resolve(resolved)
		if err != nil {
			return nil, err
		}
	}
	before, err := r.root.Lstat(resolved)
	if err != nil {
		return nil, err
	}
	if before.Mode()&os.ModeSymlink != 0 {
		return nil, prConfigurationError(description + " must not be a symbolic link")
	}
	if !before.Mode().IsRegular() {
		return nil, prConfigurationError(description + " must be a regular file")
	}
	return readSelectedFile(r, resolved, before, 0)
}

func prExplicitPath(name, description string) (*repository, string, error) {
	if secretPath(name) {
		return nil, "", prConfigurationError(description + " path is unsafe")
	}
	name, err := prExpandUser(name)
	if err != nil {
		return nil, "", err
	}
	return explicitFilePath(name, description)
}

func explicitFilePath(name, description string) (*repository, string, error) {
	if secretPath(name) {
		return nil, "", errUnsafePath
	}
	absolute, err := absoluteReferencePath(name)
	if err != nil {
		return nil, "", err
	}
	if secretPath(absolute) {
		return nil, "", prConfigurationError(description + " path is unsafe")
	}
	r, err := openRepository(filepath.VolumeName(absolute) + string(filepath.Separator))
	if err != nil {
		return nil, "", err
	}
	// The caller owns Root only after every path check succeeds.
	success := false
	defer func() {
		if !success {
			_ = r.root.Close()
		}
	}()
	relative := prefixPath(filepath.ToSlash(strings.TrimPrefix(absolute, r.absolute)))
	parentPath, leaf := ".", relative
	if parent, child, found := strings.CutLast(relative, "/"); found {
		parentPath, leaf = parent, child
	}
	parent, err := r.resolveLinkProfile(parentPath, map[string]bool{}, true)
	if err != nil {
		return nil, "", err
	}
	resolved := filepath.Join(parent, filepath.FromSlash(leaf))
	if secretPath(resolved) {
		return nil, "", prConfigurationError(description + " path is unsafe")
	}
	info, err := r.root.Stat(parent)
	if err != nil {
		return nil, "", err
	}
	if !info.IsDir() {
		return nil, "", prConfigurationError(description + " parent must be a directory")
	}
	success = true
	return r, resolved, nil
}

func prExpandUser(name string) (string, error) {
	if !filepath.IsAbs(name) {
		name = prefixPath(filepath.ToSlash(name))
	}
	if !strings.HasPrefix(name, "~") {
		return name, nil
	}
	account, rest, _ := strings.Cut(name[1:], string(filepath.Separator))
	var home string
	if account == "" {
		var err error
		home, err = prCurrentHome()
		if err != nil {
			return "", err
		}
	} else if selected, err := user.Lookup(account); err == nil {
		home = selected.HomeDir
	} else {
		return "", prConfigurationError("could not determine home directory")
	}
	return strings.TrimRight(home, string(filepath.Separator)) + string(filepath.Separator) + rest, nil
}

func prCurrentHome() (string, error) {
	if home, set := os.LookupEnv("HOME"); set {
		return home, nil
	}
	selected, err := user.Current()
	if err != nil || selected.HomeDir == "" {
		return "", prConfigurationError("could not determine home directory")
	}
	return selected.HomeDir, nil
}
