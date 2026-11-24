package module

import (
	"archive/tar"
	"errors"
	"io"
	"path"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

type treeEntry struct {
	Digest string `json:"digest,omitempty"`
	Mode   int64  `json:"mode"`
	Path   string `json:"path"`
	Size   *int64 `json:"size,omitempty"`
	Type   string `json:"type"`
}
type archiveInventory struct {
	contentDigest string
	files         map[string][]byte
	entries       []treeEntry
	metadata      []byte
}

func validArchivePath(name string, directory bool, depth int) bool {
	if directory {
		name = strings.TrimSuffix(name, "/")
	}
	if name == "" || strings.ContainsAny(name, "\x00\\") || strings.HasPrefix(name, "/") || path.Clean(name) != name {
		return false
	}
	parts := strings.Split(name, "/")
	if len(parts) > depth || len(parts[0]) == 2 && parts[0][1] == ':' {
		return false
	}
	if slices.Contains(parts, "..") {
		return false
	}
	return name != "." || directory
}

// inspectArchive has no filesystem effects. Its inventory is derived only from
// authenticated compressed bytes, before any cache path is considered.
func inspectArchive(raw []byte, contentDigest, root string, limits resourceLimits) (archiveInventory, error) {
	result := archiveInventory{files: map[string][]byte{}, contentDigest: contentDigest}
	if int64(len(raw)) > limits.bundleBytes || len(raw) == 0 {
		return result, invalid()
	}
	zip, err := openGzipSequence(raw)
	if err != nil {
		return result, invalid()
	}
	defer func() { _ = zip.Close() }()
	maximum := min(limits.tarBytes, int64(len(raw))*limits.expansionRatio)
	stream := &io.LimitedReader{R: zip, N: maximum + 1}
	reader := tar.NewReader(stream)
	inventory := archiveReader{result: result, nodes: map[string]treeEntry{".": {Mode: 0700, Path: ".", Type: termDirectory}}, seen: map[string]bool{}, limits: limits}
	for count := 0; ; count++ {
		header, readErr := reader.Next()
		if errors.Is(readErr, io.EOF) {
			break
		}
		if readErr != nil || count >= limits.members {
			return result, invalid()
		}
		if readErr = inventory.add(header, reader); readErr != nil {
			return result, readErr
		}
	}
	result = inventory.result
	nodes := inventory.nodes
	// Tar stops at its end marker; gzip must still validate its entire trailer,
	// concatenated streams and bounded trailing padding.
	if _, err = io.Copy(io.Discard, stream); err != nil || stream.N == 0 {
		return result, invalid()
	}
	return finishArchiveInventory(result, nodes, root, limits)
}
func finishArchiveInventory(result archiveInventory, nodes map[string]treeEntry, root string, limits resourceLimits) (archiveInventory, error) {
	result.entries = make([]treeEntry, 0, len(nodes))
	for _, entry := range nodes {
		result.entries = append(result.entries, entry)
	}
	slices.SortFunc(result.entries, func(a, b treeEntry) int {
		return slices.Compare(pathParts(a.Path), pathParts(b.Path))
	})
	entries, err := sortedBytes(result.entries, true)
	if err != nil {
		return result, err
	}
	result.metadata, err = sortedBytes(map[string]any{termContentDigest: result.contentDigest, "entries": result.entries, termRootFile: root, "schema": "raes-cache-tree/v1", "tree_digest": digest.SHA256(entries)}, true)
	if err != nil || int64(len(result.metadata)) > limits.metadataBytes {
		return result, invalid()
	}
	return result, nil
}

type archiveReader struct {
	result archiveInventory
	nodes  map[string]treeEntry
	seen   map[string]bool
	limits resourceLimits
	total  int64
}

func (a *archiveReader) add(header *tar.Header, reader io.Reader) error {
	directory := header.Typeflag == tar.TypeDir
	// A NUL type is the original V7 regular-file encoding.
	regular := header.Typeflag == tar.TypeReg || header.Typeflag == 0 || header.Typeflag == tar.TypeGNUSparse
	if !validArchivePath(header.Name, directory, a.limits.depth) || !directory && !regular {
		return invalid()
	}
	name := strings.TrimSuffix(header.Name, "/")
	if name == cacheManifestName || a.seen[name] {
		return invalid()
	}
	a.seen[name] = true
	if err := addArchiveParents(a.nodes, name, a.limits); err != nil {
		return err
	}
	if directory {
		return addArchiveDirectory(a.nodes, name, a.limits)
	}
	return a.addFile(header, name, reader)
}
func (a *archiveReader) addFile(header *tar.Header, name string, reader io.Reader) error {
	if _, exists := a.nodes[name]; exists || header.Size < 0 || header.Size > a.limits.memberBytes || header.Size > a.limits.totalBytes-a.total {
		return invalid()
	}
	a.total += header.Size
	data, err := io.ReadAll(io.LimitReader(reader, header.Size+1))
	if err != nil || int64(len(data)) != header.Size {
		return invalid()
	}
	mode := header.Mode & 0755
	if mode&0100 == 0 {
		mode &^= 0111
	}
	size := header.Size
	a.nodes[name] = treeEntry{Digest: digest.SHA256(data), Mode: mode | 0600, Path: name, Size: &size, Type: "file"}
	a.result.files[name] = data
	if len(a.nodes) > a.limits.members+1 {
		return invalid()
	}
	return nil
}
func pathParts(name string) []string {
	if name == "." {
		return nil
	}
	return strings.Split(name, "/")
}
func addArchiveParents(nodes map[string]treeEntry, name string, limits resourceLimits) error {
	parts := strings.Split(name, "/")
	for index := 1; index < len(parts); index++ {
		if err := addArchiveDirectory(nodes, strings.Join(parts[:index], "/"), limits); err != nil {
			return err
		}
	}
	return nil
}
func addArchiveDirectory(nodes map[string]treeEntry, name string, limits resourceLimits) error {
	if old, exists := nodes[name]; exists && old.Type != termDirectory {
		return invalid()
	}
	nodes[name] = treeEntry{Mode: 0700, Path: name, Type: termDirectory}
	if len(nodes) > limits.members+1 {
		return invalid()
	}
	return nil
}
