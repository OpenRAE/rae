package module

import (
	"bytes"
	"context"
	"errors"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

const currentPointer = ".raes-current"
const versionsDirectory = "versions"
const stagePrefix = ".staged-"
const pointerStagePrefix = ".raes-current.staged-"

func (r *Registry) publishCache(ctx context.Context, inventory archiveInventory, manifestDigest, root string) (string, error) {
	if !digest.Valid(manifestDigest) {
		return "", invalid()
	}
	slotName := strings.TrimPrefix(manifestDigest, "sha256:")
	locks, err := openDirectory(r.cache, ".locks", true)
	if err != nil {
		return "", err
	}
	defer func() { _ = locks.Close() }()
	lock, err := lockFile(ctx, locks, slotName+".lock")
	if err != nil {
		return "", err
	}
	defer func() { _ = lock.Close() }()
	slot, err := openDirectory(r.cache, slotName, true)
	if err != nil {
		return "", err
	}
	defer func() { _ = slot.Close() }()
	version, err := installVersion(slot, inventory, inventory.contentDigest, r.limits)
	if err != nil {
		return "", err
	}
	return filepath.Join(r.directory, slotName, versionsDirectory, version, filepath.FromSlash(root)), nil
}
func installVersion(slot *os.Root, inventory archiveInventory, identity string, limits resourceLimits) (string, error) {
	versions, err := openDirectory(slot, versionsDirectory, true)
	if err != nil {
		return "", err
	}
	defer func() { _ = versions.Close() }()
	previous := currentVersion(slot, versions)
	if err = cleanInterruptedStages(slot, versions); err != nil {
		return "", err
	}
	version, err := recoverVersion(slot, versions, inventory, identity, limits)
	if err != nil {
		return "", err
	}
	if version == "" {
		version, err = stageVersion(versions, inventory, identity)
		if err != nil {
			return "", err
		}
	}
	if err = commitVersion(slot, versions, version, previous); err != nil {
		return "", err
	}
	return version, nil
}
func validVersion(name string) bool {
	if name == "" || len(name) > 200 {
		return false
	}
	for index, char := range name {
		letter := char >= 'a' && char <= 'z' || char >= 'A' && char <= 'Z' || char >= '0' && char <= '9'
		if !letter && (index == 0 || char != '.' && char != '_' && char != '-') {
			return false
		}
	}
	return true
}
func recoverVersion(slot, versions *os.Root, inventory archiveInventory, identity string, limits resourceLimits) (string, error) {
	current := currentVersion(slot, versions)
	if current != "" && validCachedVersion(versions, current, inventory, limits) {
		return current, nil
	}
	prefix, tagged := strings.CutPrefix(identity, "sha256:")
	if !tagged || len(prefix) != 64 {
		return "", invalid()
	}
	prefix = prefix[:20] + "-"
	maximum := 64
	if current != "" {
		maximum--
	}
	names := []string{}
	err := eachVersionDirectory(versions, func(name string, _ fs.FileInfo) error {
		if name == current || !strings.HasPrefix(name, prefix) {
			return nil
		}
		names = append(names, name)
		slices.Sort(names)
		if len(names) > maximum {
			names = names[:maximum]
		}
		return nil
	})
	if err != nil {
		return "", err
	}
	for _, name := range names {
		if validVersion(name) && validCachedVersion(versions, name, inventory, limits) {
			return name, nil
		}
	}
	return "", nil
}
func boundedDirectoryNames(root *os.Root, limit int) ([]string, error) {
	directory, err := root.Open(".")
	if err != nil {
		return nil, operational(err)
	}
	defer func() { _ = directory.Close() }()
	names, err := directory.Readdirnames(limit + 1)
	if err != nil && !errors.Is(err, io.EOF) {
		return nil, operational(err)
	}
	if len(names) > limit {
		return nil, invalid()
	}
	return names, nil
}
func validCachedVersion(versions *os.Root, name string, inventory archiveInventory, limits resourceLimits) bool {
	version, err := openDirectory(versions, name, false)
	if err != nil {
		return false
	}
	defer func() { _ = version.Close() }()
	if inventory.metadata != nil {
		metadata, info, metadataErr := readRegular(version, cacheManifestName, limits.metadataBytes)
		if metadataErr != nil || !info.Mode().IsRegular() || !bytes.Equal(metadata, inventory.metadata) {
			return false
		}
	}
	expected := make(map[string]treeEntry, len(inventory.entries))
	for _, entry := range inventory.entries {
		expected[entry.Path] = entry
	}
	rootInfo, err := fs.Stat(version.FS(), ".")
	if err != nil || inventory.metadata != nil && !cacheModeMatches(rootInfo.Mode(), expected["."].Mode) {
		return false
	}
	check := cacheCheck{expected: expected, limits: limits, metadata: inventory.metadata != nil}
	err = check.directory(version, ".")
	return err == nil && check.count == len(expected)
}

type cacheCheck struct {
	expected map[string]treeEntry
	limits   resourceLimits
	metadata bool
	count    int
}

func (c *cacheCheck) directory(directory *os.Root, prefix string) error {
	c.count++
	children, err := boundedDirectoryNames(directory, len(c.expected)+1)
	if err != nil {
		return err
	}
	for _, name := range children {
		if c.metadata && prefix == "." && name == cacheManifestName {
			continue
		}
		relative := name
		if prefix != "." {
			relative = prefix + "/" + name
		}
		wanted, exists := c.expected[relative]
		if !exists {
			return invalid()
		}
		if err = c.entry(directory, name, relative, wanted); err != nil {
			return err
		}
	}
	return nil
}
func (c *cacheCheck) entry(directory *os.Root, name, relative string, wanted treeEntry) error {
	info, err := directory.Lstat(name)
	if err != nil || c.metadata && !cacheModeMatches(info.Mode(), wanted.Mode) {
		return invalid()
	}
	if wanted.Type == termDirectory {
		child, openErr := openDirectory(directory, name, false)
		if openErr != nil {
			return openErr
		}
		defer func() { _ = child.Close() }()
		return c.directory(child, relative)
	}
	if !info.Mode().IsRegular() || wanted.Size == nil || info.Size() != *wanted.Size {
		return invalid()
	}
	raw, opened, err := readRegular(directory, name, c.limits.memberBytes)
	if err != nil || !os.SameFile(info, opened) || digest.SHA256(raw) != wanted.Digest {
		return invalid()
	}
	c.count++
	return nil
}
func stageVersion(versions *os.Root, inventory archiveInventory, identity string) (string, error) {
	if !digest.Valid(identity) {
		return "", invalid()
	}
	id, err := nonce()
	if err != nil {
		return "", err
	}
	stageName := stagePrefix + id
	if err = versions.Mkdir(stageName, 0700); err != nil {
		return "", operational(err)
	}
	stage, err := openDirectory(versions, stageName, false)
	if err != nil {
		return "", err
	}
	defer func() { _ = stage.Close() }()
	defer func() { _ = versions.RemoveAll(stageName) }()
	if err = writeStageInventory(stage, inventory); err != nil {
		return "", err
	}
	if err = syncStageDirectories(stage, inventory.entries); err != nil {
		return "", err
	}
	version := strings.TrimPrefix(identity, "sha256:")[:20] + "-" + id
	if err = versions.Rename(stageName, version); err != nil {
		return "", operational(err)
	}
	if err = syncDirectory(versions); err != nil {
		return "", err
	}
	return version, nil
}
func writeStageInventory(stage *os.Root, inventory archiveInventory) error {
	for _, entry := range inventory.entries {
		if entry.Path == "." {
			continue
		}
		if entry.Type == termDirectory {
			directory, err := openDirectory(stage, entry.Path, true)
			if err != nil {
				return err
			}
			_ = directory.Close()
			continue
		}
		if entry.Mode < 0 || entry.Mode > 0777 {
			return invalid()
		}
		if err := writeExclusive(stage, entry.Path, inventory.files[entry.Path], fs.FileMode(entry.Mode)); err != nil {
			return err
		}
	}
	if inventory.metadata != nil {
		return writeExclusive(stage, cacheManifestName, inventory.metadata, 0600)
	}
	return nil
}
func syncStageDirectories(stage *os.Root, entries []treeEntry) error {
	// Flush child directories before making the immutable version discoverable.
	for _, entry := range slices.Backward(entries) {
		if entry.Type != termDirectory {
			continue
		}
		directory, err := openDirectory(stage, entry.Path, false)
		if err != nil {
			return err
		}
		syncErr := syncDirectory(directory)
		_ = directory.Close()
		if syncErr != nil {
			return syncErr
		}
	}
	return nil
}
func replacePointer(slot *os.Root, version string) error {
	id, err := nonce()
	if err != nil {
		return err
	}
	temporary := pointerStagePrefix + id
	defer func() { _ = slot.Remove(temporary) }()
	if err = writeExclusive(slot, temporary, []byte(version+"\n"), 0600); err != nil {
		return err
	}
	if err = slot.Rename(temporary, currentPointer); err != nil {
		return operational(err)
	}
	return syncDirectory(slot)
}
func cacheModeMatches(mode fs.FileMode, wanted int64) bool {
	return mode&(os.ModeSetuid|os.ModeSetgid|os.ModeSticky) == 0 && int64(mode.Perm()) == wanted
}
func cleanInterruptedStages(slot, versions *os.Root) error {
	for _, target := range []struct {
		root   *os.Root
		prefix string
	}{{slot, pointerStagePrefix}, {versions, stagePrefix}} {
		err := eachDirectoryName(target.root, func(name string) error {
			if strings.HasPrefix(name, target.prefix) {
				if err := target.root.RemoveAll(name); err != nil {
					return operational(err)
				}
			}
			return nil
		})
		if err != nil {
			return err
		}
	}
	return nil
}
