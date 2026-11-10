package module

import (
	"archive/tar"
	"bytes"
	"context"
	"crypto/ed25519"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

// PublicationAdmitter is the native source and composition owner. It returns
// the canonical entrypoint and captured bytes that it actually checked.
type PublicationAdmitter interface {
	AdmitModuleSources(ctx context.Context, source fs.FS, root string) (string, map[string][]byte, error)
}

// Publish writes a deterministic local OCI layout from admitted source bytes.
// Private key bytes are caller supplied; this operation has no key-file access.
func (r *Registry) Publish(ctx context.Context, source fs.FS, root, outputDirectory, signerID string, privateKey []byte, admitter PublicationAdmitter) (Publication, error) {
	if r == nil || admitter == nil {
		return Publication{}, invalid()
	}
	entry, files, err := admitter.AdmitModuleSources(ctx, source, root)
	if err != nil {
		return Publication{}, err
	}
	if !validArchivePath(entry, false, r.limits.depth) {
		return Publication{}, invalid()
	}
	descriptor, err := r.sourceDescriptor(files[entry])
	if err != nil {
		return Publication{}, err
	}
	bundle, err := buildBundle(files, r.limits)
	if err != nil {
		return Publication{}, err
	}
	contentDigest := digest.SHA256(bundle)
	signatures, err := buildSignatures(descriptor, contentDigest, entry, signerID, privateKey)
	if err != nil {
		return Publication{}, err
	}
	config, err := sortedBytes(map[string]any{termSchemaVersion: "raes-module-oci/v1", termRootFile: entry, "module": descriptor, "signatures": signatures}, false)
	if err != nil {
		return Publication{}, err
	}
	configDigest := digest.SHA256(config)
	manifest := ociManifest{SchemaVersion: 2, MediaType: manifestMediaType, Config: blobDescriptor{MediaType: configMediaType, Digest: configDigest, Size: int64(len(config))}, Layers: []blobDescriptor{{MediaType: bundleMediaType, Digest: contentDigest, Size: int64(len(bundle))}}, Annotations: map[string]string{"org.opencontainers.image.ref.name": descriptor.Version, "io.raes.module.id": descriptor.ID}}
	manifestBytes, err := sortedBytes(manifest, false)
	if err != nil {
		return Publication{}, err
	}
	manifestDigest := digest.SHA256(manifestBytes)
	index, err := prettyBytes(map[string]any{"schemaVersion": 2, "manifests": []any{map[string]any{"mediaType": manifestMediaType, "digest": manifestDigest, "size": len(manifestBytes), "annotations": manifest.Annotations}}})
	if err != nil {
		return Publication{}, err
	}
	layoutFiles := map[string][]byte{"oci-layout": []byte("{\"imageLayoutVersion\":\"1.0.0\"}\n"), "index.json": index}
	for hash, raw := range map[string][]byte{configDigest: config, contentDigest: bundle, manifestDigest: manifestBytes} {
		layoutFiles["blobs/sha256/"+strings.TrimPrefix(hash, "sha256:")] = raw
	}
	slotName := strings.ReplaceAll(descriptor.ID, "/", "_") + "-" + descriptor.Version + ".oci"
	if !fs.ValidPath(slotName) || strings.ContainsAny(slotName, "/\\\x00") {
		return Publication{}, invalid()
	}
	layout, err := publishLayout(ctx, outputDirectory, slotName, layoutFiles, manifestDigest, r.limits)
	if err != nil {
		return Publication{}, err
	}
	exports, err := sortedBytes(descriptor.Exports, false)
	if err != nil {
		return Publication{}, err
	}
	return Publication{LayoutDir: layout, ModuleID: descriptor.ID, ModuleVersion: descriptor.Version, ManifestDigest: manifestDigest, ContentDigest: contentDigest, ExportHash: strings.TrimPrefix(digest.SHA256(exports), "sha256:"), SignerID: signerID}, nil
}
func buildSignatures(descriptor moduleDescriptor, contentDigest, root, signerID string, privateKey []byte) ([]signatureRecord, error) {
	result := []signatureRecord{}
	if (signerID != "") != (len(privateKey) > 0) || pythonTrim(signerID) != signerID {
		return nil, invalid()
	}
	if signerID == "" {
		return result, nil
	}
	block, rest := pem.Decode(privateKey)
	if block == nil || block.Type != "PRIVATE KEY" || len(bytes.TrimSpace(rest)) != 0 {
		return nil, invalid()
	}
	parsed, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, invalid()
	}
	key, ok := parsed.(ed25519.PrivateKey)
	if !ok {
		return nil, invalid()
	}
	payload, err := signablePayload(descriptor, contentDigest, root)
	if err != nil {
		return nil, err
	}
	return append(result, signatureRecord{Signer: signerID, Signature: base64.StdEncoding.EncodeToString(ed25519.Sign(key, payload))}), nil
}

type boundedWriter struct {
	writer             io.Writer
	remaining, written int64
}

func (w *boundedWriter) Write(raw []byte) (int, error) {
	if int64(len(raw)) > w.remaining {
		return 0, invalid()
	}
	n, err := w.writer.Write(raw)
	w.remaining -= int64(n)
	w.written += int64(n)
	return n, err
}
func buildBundle(files map[string][]byte, limits resourceLimits) ([]byte, error) {
	if len(files) == 0 || len(files) > limits.members {
		return nil, invalid()
	}
	names, err := bundleNames(files, limits)
	if err != nil {
		return nil, err
	}
	var result bytes.Buffer
	stream := &boundedWriter{writer: &result, remaining: limits.tarBytes}
	profile := &tarProfile{output: stream}
	writer := tar.NewWriter(profile)
	for _, name := range names {
		if err = writeBundleFile(writer, profile, name, files[name]); err != nil {
			return nil, err
		}
	}
	if err = writer.Close(); err != nil {
		return nil, invalid()
	}
	if remainder := stream.written % 10240; remainder != 0 {
		if _, err = stream.Write(make([]byte, 10240-remainder)); err != nil {
			return nil, invalid()
		}
	}
	compressed, err := publisherGzip(result.Bytes(), limits.bundleBytes)
	if err != nil {
		return nil, err
	}
	if _, err = inspectArchive(compressed, digest.SHA256(compressed), names[0], limits); err != nil {
		return nil, err
	}
	return compressed, nil
}
func writeBundleFile(writer *tar.Writer, profile *tarProfile, name string, raw []byte) error {
	profile.name = name
	header := &tar.Header{Name: name, Mode: 0644, Size: int64(len(raw)), Typeflag: tar.TypeReg, Format: tar.FormatPAX}
	if len(name) > 100 || asciiName(name) != name {
		header.PAXRecords = map[string]string{"path": name}
	}
	if err := writer.WriteHeader(header); err != nil {
		return invalid()
	}
	if _, err := writer.Write(raw); err != nil {
		return invalid()
	}
	return nil
}
func bundleNames(files map[string][]byte, limits resourceLimits) ([]string, error) {
	names := make([]string, 0, len(files))
	var total int64
	for name, raw := range files {
		if !validArchivePath(name, false, limits.depth) || name == cacheManifestName || int64(len(raw)) > limits.memberBytes || int64(len(raw)) > limits.totalBytes-total {
			return nil, invalid()
		}
		total += int64(len(raw))
		names = append(names, name)
	}
	slices.Sort(names)
	return names, nil
}
func prettyBytes(value any) ([]byte, error) {
	raw, err := sortedBytes(value, false)
	if err != nil {
		return nil, err
	}
	var output bytes.Buffer
	if err = json.Indent(&output, raw, "", "  "); err != nil {
		return nil, err
	}
	output.WriteByte('\n')
	return output.Bytes(), nil
}
func publishLayout(ctx context.Context, outputDirectory, slotName string, files map[string][]byte, identity string, limits resourceLimits) (string, error) {
	if outputDirectory == "" {
		return "", invalid()
	}
	if err := os.MkdirAll(outputDirectory, 0700); err != nil {
		return "", operational(err)
	}
	before, err := os.Lstat(outputDirectory)
	if err != nil || !before.IsDir() || before.Mode()&os.ModeSymlink != 0 {
		return "", invalid()
	}
	output, err := os.OpenRoot(outputDirectory)
	if err != nil {
		return "", operational(err)
	}
	defer func() { _ = output.Close() }()
	after, err := fs.Stat(output.FS(), ".")
	if err != nil || !os.SameFile(before, after) {
		return "", invalid()
	}
	locks, err := openDirectory(output, ".raes-layout-locks", true)
	if err != nil {
		return "", err
	}
	defer func() { _ = locks.Close() }()
	lock, err := lockFile(ctx, locks, slotName+".lock")
	if err != nil {
		return "", err
	}
	defer func() { _ = lock.Close() }()
	slot, err := openDirectory(output, slotName, true)
	if err != nil {
		return "", err
	}
	defer func() { _ = slot.Close() }()
	if err = checkLegacyLayout(slot); err != nil {
		return "", err
	}
	inventory, err := layoutInventory(files, limits)
	if err != nil {
		return "", err
	}
	version, err := installVersion(slot, inventory, identity, limits)
	if err != nil {
		return "", err
	}
	absolute, err := filepath.Abs(outputDirectory)
	if err != nil {
		return "", operational(err)
	}
	return filepath.Join(absolute, slotName, versionsDirectory, version), nil
}
func checkLegacyLayout(slot *os.Root) error {
	for _, name := range []string{"oci-layout", "index.json", "blobs"} {
		if _, err := slot.Lstat(name); err == nil {
			return fault.New(fault.Conflict, "sdl-module-layout-legacy", nil)
		} else if !os.IsNotExist(err) {
			return operational(err)
		}
	}
	return nil
}
func layoutInventory(files map[string][]byte, limits resourceLimits) (archiveInventory, error) {
	result := archiveInventory{files: files}
	nodes := map[string]treeEntry{".": {Path: ".", Type: termDirectory, Mode: 0700}}
	for name, raw := range files {
		if err := addArchiveParents(nodes, name, limits); err != nil {
			return result, err
		}
		size := int64(len(raw))
		nodes[name] = treeEntry{Path: name, Type: "file", Mode: 0644, Size: &size, Digest: digest.SHA256(raw)}
	}
	for _, entry := range nodes {
		result.entries = append(result.entries, entry)
	}
	slices.SortFunc(result.entries, func(a, b treeEntry) int { return slices.Compare(pathParts(a.Path), pathParts(b.Path)) })
	return result, nil
}
