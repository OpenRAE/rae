package arch

import (
	"fmt"
	"strings"
	"testing"
	"testing/fstest"
)

func TestAPIFileCountUsesTheInclusiveDeclaredLimit(t *testing.T) {
	paths := make([]string, 64)
	for index := range paths {
		paths[index] = apiFixturePath
	}
	repo := fstest.MapFS{apiFixturePath: {Data: []byte(`["package x"]`)}}
	m := &Model{Packages: []Package{{APIFiles: map[string][]string{"linux": paths[:32], "windows": paths[32:]}}}}
	if err := m.loadAPIFiles(repo); err != nil {
		t.Fatal("rejected exactly 64 files", err)
	}
	m = &Model{Packages: []Package{{APIFiles: map[string][]string{"linux": paths[:32], "windows": append(paths[32:], apiFixturePath)}}}}
	if err := m.loadAPIFiles(repo); err == nil {
		t.Fatal("accepted more than 64 files across configurations")
	}
}

func TestAPIFileTotalBudgetIsSharedAcrossPackages(t *testing.T) {
	repo := fstest.MapFS{}
	paths := []string{}
	remaining := 16777216
	for index := 0; remaining > 0; index++ {
		size := min(512000, remaining)
		path := fmt.Sprintf("implementations/architecture-api/budget-%02d.json", index)
		value := `["package x"]`
		repo[path] = &fstest.MapFile{Data: []byte(value + strings.Repeat(" ", size-len(value)))}
		paths = append(paths, path)
		remaining -= size
	}
	model := func() *Model {
		return &Model{Packages: []Package{{APIFiles: map[string][]string{"linux": paths[:16]}}, {APIFiles: map[string][]string{"linux": paths[16:]}}}}
	}
	if err := model().loadAPIFiles(repo); err != nil {
		t.Fatal("rejected exactly 16 MiB", err)
	}
	last := repo[paths[len(paths)-1]]
	last.Data = append(last.Data, ' ')
	if err := model().loadAPIFiles(repo); err == nil {
		t.Fatal("budget was not shared across packages")
	}
}
