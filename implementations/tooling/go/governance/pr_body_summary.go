package governance

import (
	"errors"
	"io/fs"
	"os"
)

func prWriteSummary(name, text string) error {
	r, destination, err := prExplicitPath(name, "summary file")
	if err != nil {
		return prConfigurationError(err.Error())
	}
	defer func() { _ = r.root.Close() }()
	file, err := prSummaryFile(r, destination)
	if err != nil {
		return prConfigurationError(err.Error())
	}
	err = file.Truncate(0)
	if err == nil {
		_, err = file.WriteString(text)
	}
	if writeErr := errors.Join(err, file.Close()); writeErr != nil {
		return prConfigurationError(writeErr.Error())
	}
	return nil
}

func prSummaryFile(r *repository, name string) (*os.File, error) {
	before, err := r.root.Lstat(name)
	flags := os.O_WRONLY
	switch {
	case errors.Is(err, fs.ErrNotExist):
		flags |= os.O_CREATE | os.O_EXCL
	case err != nil:
		return nil, err
	case !before.Mode().IsRegular():
		return nil, prConfigurationError("summary file must be a regular file and not a symbolic link")
	}
	// Bind the regular inode before truncating it. Existing-file permissions,
	// metadata and hard links retain the reference's ordinary-write semantics.
	file, err := r.root.OpenFile(name, flags, 0o666)
	if err != nil {
		return nil, err
	}
	opened, err := file.Stat()
	if err != nil {
		_ = file.Close()
		return nil, err
	}
	if !opened.Mode().IsRegular() || before != nil && !os.SameFile(before, opened) {
		_ = file.Close()
		return nil, prConfigurationError("summary file changed before it could be written")
	}
	return file, nil
}
