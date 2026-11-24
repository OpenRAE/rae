package governance

import (
	"io"
	"os"
	"path/filepath"
	"syscall"
)

func readSelectedFile(r *repository, name string, before os.FileInfo, limit int64) ([]byte, error) {
	if !repositoryPath(name) {
		return nil, errUnsafePath
	}
	file, err := os.OpenFile(filepath.Join(r.absolute, name), os.O_RDONLY|syscall.O_NOFOLLOW, 0) // #nosec G304 G703 -- Explicitly selected path with checked parents; O_NOFOLLOW and inode checks bind the final file before content is read.
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	opened, err := file.Stat()
	if err != nil {
		return nil, err
	}
	if !os.SameFile(before, opened) || !opened.Mode().IsRegular() {
		return nil, prConfigurationError("selected input changed before it was read")
	}
	if limit > 0 && opened.Size() > limit {
		return nil, prConfigurationError("selected input exceeds its byte limit")
	}
	var reader io.Reader = file
	if limit > 0 {
		reader = io.LimitReader(file, limit+1)
	}
	data, err := io.ReadAll(reader)
	if err != nil {
		return nil, err
	}
	after, err := r.root.Lstat(name)
	if err != nil {
		return nil, err
	}
	if !os.SameFile(opened, after) || limit > 0 && (int64(len(data)) > limit || int64(len(data)) != opened.Size()) {
		return nil, prConfigurationError("selected input changed while it was read")
	}
	return data, nil
}
