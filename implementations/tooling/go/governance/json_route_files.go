package governance

import (
	"io/fs"
	"os"
	"slices"
	"strings"
)

func regularRepoFile(r *repository, name string) bool {
	info, err := noLinkInfo(r, name)
	return err == nil && info.Mode().IsRegular()
}

func noLinkInfo(r *repository, name string) (fs.FileInfo, error) {
	if !repositoryPath(name) {
		return nil, errUnsafePath
	}
	parts := strings.Split(strings.TrimSuffix(name, "/"), "/")
	var info fs.FileInfo
	for i := range parts {
		var err error
		info, err = r.root.Lstat(strings.Join(parts[:i+1], "/"))
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 || i < len(parts)-1 && !info.IsDir() {
			return nil, errUnsafePath
		}
	}
	return info, nil
}

func discoverJSON(r *repository, prefix string, recursive bool) []string {
	directory := strings.TrimSuffix(prefix, "/")
	info, err := noLinkInfo(r, directory)
	if err != nil || !info.IsDir() {
		return nil
	}
	names := []string{}
	_ = fs.WalkDir(r.root.FS(), directory, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return nil //nolint:nilerr // Path.glob/rglob ignore unreadable candidate subtrees.
		}
		if entry.IsDir() {
			if secretPath(name) || name != directory && !recursive {
				return fs.SkipDir
			}
			return nil
		}
		if !secretPath(name) && strings.HasSuffix(name, ".json") && regularRepoFile(r, name) {
			names = append(names, name)
		}
		return nil
	})
	slices.Sort(names)
	return names
}
