package module

import (
	"errors"
	"io"
	"io/fs"
	"os"
	"slices"
	"strings"
)

func currentVersion(slot, versions *os.Root) string {
	raw, _, err := readRegular(slot, currentPointer, 256)
	if err != nil {
		return ""
	}
	name := strings.TrimSpace(string(raw))
	if !validVersion(name) {
		return ""
	}
	info, err := versions.Lstat(name)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return ""
	}
	return name
}

// Enumeration retains a fixed number of names in memory. Recovery still
// examines the reference's first 64 sorted directory candidates, regardless
// of unrelated stages or the number of old versions on disk.
func eachDirectoryName(root *os.Root, visit func(string) error) error {
	directory, err := root.Open(".")
	if err != nil {
		return operational(err)
	}
	defer func() { _ = directory.Close() }()
	for {
		names, err := directory.Readdirnames(64)
		if err != nil && !errors.Is(err, io.EOF) {
			return operational(err)
		}
		for _, name := range names {
			if visitErr := visit(name); visitErr != nil {
				return visitErr
			}
		}
		if errors.Is(err, io.EOF) {
			return nil
		}
	}
}
func eachVersionDirectory(root *os.Root, visit func(string, fs.FileInfo) error) error {
	return eachDirectoryName(root, func(name string) error {
		if !validVersion(name) {
			return nil
		}
		info, err := root.Lstat(name)
		if err != nil {
			return operational(err)
		}
		if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return nil
		}
		return visit(name, info)
	})
}

type rankedVersion struct {
	name string
	info fs.FileInfo
}

func commitVersion(slot, versions *os.Root, current, previous string) error {
	if err := pruneVersions(versions, current, previous); err != nil {
		return err
	}
	return replacePointer(slot, current)
}

func pruneVersions(versions *os.Root, current, previous string) error {
	retained := map[string]bool{current: true}
	if previous != "" {
		retained[previous] = true
	}
	remaining := 8 - len(retained)
	newest := []rankedVersion{}
	err := eachVersionDirectory(versions, func(name string, info fs.FileInfo) error {
		if retained[name] {
			return nil
		}
		newest = append(newest, rankedVersion{name, info})
		slices.SortFunc(newest, func(a, b rankedVersion) int {
			if order := b.info.ModTime().Compare(a.info.ModTime()); order != 0 {
				return order
			}
			return strings.Compare(b.name, a.name)
		})
		if len(newest) <= remaining {
			return nil
		}
		oldest := newest[len(newest)-1].name
		newest = newest[:remaining]
		if err := versions.RemoveAll(oldest); err != nil {
			return operational(err)
		}
		return nil
	})
	if err != nil {
		return err
	}
	return syncDirectory(versions)
}
