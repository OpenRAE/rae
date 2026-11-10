package module

import (
	"crypto/rand"
	"encoding/hex"
	"io"
	"io/fs"
	"os"
	"strings"
	"syscall"
)

func openDirectory(parent *os.Root, name string, create bool) (*os.Root, error) {
	if strings.Contains(name, "/") {
		parts := strings.SplitN(name, "/", 2)
		ancestor, err := openDirectory(parent, parts[0], false)
		if err != nil {
			return nil, err
		}
		defer func() { _ = ancestor.Close() }()
		return openDirectory(ancestor, parts[1], create)
	}
	if create {
		if err := parent.Mkdir(name, 0700); err != nil && !os.IsExist(err) {
			return nil, operational(err)
		}
	}
	before, err := parent.Lstat(name)
	if err != nil {
		return nil, operational(err)
	}
	if !before.IsDir() {
		return nil, invalid()
	}
	opened, err := parent.OpenRoot(name)
	if err != nil {
		return nil, operational(err)
	}
	after, err := fs.Stat(opened.FS(), ".")
	if err != nil || !os.SameFile(before, after) {
		_ = opened.Close()
		return nil, invalid()
	}
	return opened, nil
}
func openParent(root *os.Root, name string) (*os.Root, string, error) {
	parts := strings.Split(name, "/")
	current, err := openDirectory(root, ".", false)
	if err != nil {
		return nil, "", err
	}
	for _, part := range parts[:len(parts)-1] {
		next, err := openDirectory(current, part, false)
		_ = current.Close()
		if err != nil {
			return nil, "", err
		}
		current = next
	}
	return current, parts[len(parts)-1], nil
}
func readRegular(root *os.Root, name string, limit int64) ([]byte, fs.FileInfo, error) {
	parent, leaf, err := openParent(root, name)
	if err != nil {
		return nil, nil, err
	}
	defer func() { _ = parent.Close() }()
	before, err := parent.Lstat(leaf)
	if err != nil {
		return nil, nil, operational(err)
	}
	if !before.Mode().IsRegular() || before.Size() > limit {
		return nil, nil, invalid()
	}
	handle, err := parent.OpenFile(leaf, os.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_NONBLOCK, 0)
	if err != nil {
		return nil, nil, operational(err)
	}
	defer func() { _ = handle.Close() }()
	opened, err := handle.Stat()
	if err != nil || !os.SameFile(before, opened) || opened.Mode() != before.Mode() || opened.Size() != before.Size() {
		return nil, nil, invalid()
	}
	raw, err := io.ReadAll(io.LimitReader(handle, limit+1))
	after, statErr := handle.Stat()
	if err != nil || statErr != nil || int64(len(raw)) != before.Size() || !os.SameFile(opened, after) || after.Size() != opened.Size() || after.Mode() != opened.Mode() {
		return nil, nil, invalid()
	}
	return raw, after, nil
}
func writeExclusive(root *os.Root, name string, raw []byte, mode fs.FileMode) error {
	parent, leaf, err := openParent(root, name)
	if err != nil {
		return err
	}
	defer func() { _ = parent.Close() }()
	handle, err := parent.OpenFile(leaf, os.O_CREATE|os.O_EXCL|os.O_WRONLY|syscall.O_NOFOLLOW, mode)
	if err != nil {
		return operational(err)
	}
	defer func() { _ = handle.Close() }()
	if err = handle.Chmod(mode); err != nil {
		return operational(err)
	}
	if _, err = handle.Write(raw); err != nil {
		return operational(err)
	}
	if err = handle.Sync(); err != nil {
		return operational(err)
	}
	if err = handle.Close(); err != nil {
		return operational(err)
	}
	return nil
}
func syncDirectory(root *os.Root) error {
	handle, err := root.Open(".")
	if err != nil {
		return operational(err)
	}
	defer func() { _ = handle.Close() }()
	if err = handle.Sync(); err != nil {
		return operational(err)
	}
	return nil
}
func nonce() (string, error) {
	var value [10]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", operational(err)
	}
	return hex.EncodeToString(value[:]), nil
}
