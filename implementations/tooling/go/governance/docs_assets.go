package governance

import (
	"crypto/sha256"
	"encoding/hex"
	"io"
	"os"
	"path"
	"path/filepath"
	"strings"
)

func publicAssetFindings(r *repository, root, output string, entries []documentationEntry) ([]Finding, error) {
	digests, err := publicSourceDigests(r, root, output, entries)
	if err != nil {
		return nil, err
	}
	findings := []Finding{}
	for _, directory := range []string{"_downloads", "_images"} {
		assets, err := publicAssetDirectoryFindings(r, output, directory, digests)
		if err != nil {
			return nil, err
		}
		findings = append(findings, assets...)
	}
	return findings, nil
}

func publicSourceDigests(r *repository, root, output string, entries []documentationEntry) (map[string]bool, error) {
	digests := map[string]bool{}
	outputAbsolute := filepath.Join(r.absolute, output)
	for _, entry := range entries {
		if !entry.info.Mode().IsRegular() || strings.Split(strings.TrimPrefix(entry.name, root+"/"), "/")[0] == "_build" {
			continue
		}
		resolved, err := r.resolve(entry.name)
		if err != nil {
			return nil, err
		}
		absolute := filepath.Join(r.absolute, resolved)
		if absolute != outputAbsolute && containedDocumentPath(outputAbsolute, absolute) {
			continue
		}
		digest, err := publicFileDigest(r, entry.name)
		if err != nil {
			return nil, err
		}
		digests[digest] = true
	}
	return digests, nil
}

func publicAssetDirectoryFindings(r *repository, output, directory string, digests map[string]bool) ([]Finding, error) {
	findings := []Finding{}
	entries, err := documentationEntries(r, path.Join(output, directory))
	if err != nil {
		return nil, err
	}
	for _, asset := range entries {
		if asset.info.IsDir() {
			continue
		}
		if !r.file(asset.name) {
			if asset.info.Mode()&os.ModeSymlink != 0 && !r.safe(asset.name) {
				return nil, errUnsafePath
			}
			continue
		}
		digest, err := publicFileDigest(r, asset.name)
		if err != nil {
			return nil, err
		}
		if !digests[digest] {
			findings = append(findings, finding("public-docs-output-asset", "published download or image has no byte-identical source beneath docs/public", strings.TrimPrefix(asset.name, output+"/")))
		}
	}
	return findings, nil
}

func publicFileDigest(r *repository, name string) (string, error) {
	resolved, err := r.resolve(name)
	if err != nil {
		return "", err
	}
	file, err := r.root.Open(resolved)
	if err != nil {
		return "", err
	}
	defer func() { _ = file.Close() }()
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}
