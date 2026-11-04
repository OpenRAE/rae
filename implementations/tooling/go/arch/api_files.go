package arch

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"strings"
)

const (
	apiFileLimit      = 512_000    // 500 KiB
	apiTotalLimit     = 16_777_216 // 16 MiB
	apiFileCountLimit = 64
)

// Expand bounded repository-owned snapshots before the existing exact checks.
// The model and the expanded declarations retain their separate read bounds.
func (m *Model) loadAPIFiles(repo fs.FS) error {
	remaining := apiTotalLimit
	for index := range m.Packages {
		pkg := &m.Packages[index]
		if len(pkg.APIFiles) == 0 {
			continue
		}
		api, err := packageAPIFiles(repo, pkg, &remaining)
		if err != nil {
			return err
		}
		pkg.API = api
	}
	return nil
}

func readAPIFile(repo fs.FS, path string, remaining *int) ([]string, error) {
	if !fs.ValidPath(path) || !strings.HasPrefix(path, "implementations/architecture-api/") || !strings.HasSuffix(path, ".json") {
		return nil, errors.New("unsafe API snapshot path")
	}
	file, err := repo.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	content, err := io.ReadAll(io.LimitReader(file, apiFileLimit+1))
	if err != nil {
		return nil, err
	}
	*remaining -= len(content)
	if len(content) > apiFileLimit || *remaining < 0 {
		return nil, errors.New("API snapshot read budget exceeded")
	}
	var declarations []string
	decoder := json.NewDecoder(bytes.NewReader(content))
	if err = decoder.Decode(&declarations); err != nil {
		return nil, err
	}
	if _, err = decoder.Token(); !errors.Is(err, io.EOF) {
		return nil, errors.New("data follows API snapshot")
	}
	if len(declarations) == 0 {
		return nil, errors.New("empty API snapshot")
	}
	return declarations, nil
}

func packageAPIFiles(repo fs.FS, pkg *Package, remaining *int) (map[string][]string, error) {
	if pkg.API != nil {
		return nil, errors.New("package declares both api and api_files")
	}
	api := map[string][]string{}
	count := 0
	for config, paths := range pkg.APIFiles {
		count += len(paths)
		if len(paths) == 0 || count > apiFileCountLimit {
			return nil, errors.New("invalid API snapshot file count")
		}
		declarations := []string{}
		for _, path := range paths {
			rows, err := readAPIFile(repo, path, remaining)
			if err != nil {
				return nil, fmt.Errorf("API snapshot: %w", err)
			}
			declarations = append(declarations, rows...)
		}
		api[config] = declarations
	}
	return api, nil
}
