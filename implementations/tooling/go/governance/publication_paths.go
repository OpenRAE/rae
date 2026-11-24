package governance

import (
	"io/fs"
	"strings"
)

func publicationSchemaPath(r *repository, name string) (string, error) {
	if secretPath(name) || strings.HasPrefix(name, "/") {
		return "", errUnsafePath
	}
	root, err := r.resolve(strings.TrimSuffix(schemasPrefix, "/"))
	if err != nil {
		return "", err
	}
	// Path.resolve applies '..' after following the preceding link. Collapsing
	// the candidate first would silently select a different schema.
	resolved, err := r.resolveLinks(name, map[string]bool{})
	if err != nil {
		return "", err
	}
	if resolved != root && !strings.HasPrefix(resolved, root+"/") {
		return "", errUnsafePath
	}
	return resolved, nil
}

// Publication inventory includes matching directories and dangling links.
// Corpus/evidence discovery has the different, regular-file-only profile.
func publicationSchemaPaths(r *repository) (map[string]bool, error) {
	directory, err := r.resolve(strings.TrimSuffix(schemasPrefix, "/"))
	if err != nil {
		return nil, err
	}
	names := map[string]bool{}
	_ = fs.WalkDir(r.root.FS(), directory, func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return nil //nolint:nilerr // Path.rglob ignores unreadable inventory subtrees.
		}
		if secretPath(name) {
			if entry.IsDir() {
				return fs.SkipDir
			}
			return nil
		}
		if name != directory && strings.HasSuffix(name, ".json") {
			names[schemasPrefix+strings.TrimPrefix(name, directory+"/")] = true
		}
		return nil
	})
	return names, nil
}
