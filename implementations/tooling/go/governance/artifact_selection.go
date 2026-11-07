package governance

import (
	"encoding/hex"
	"encoding/json"
	"slices"
	"strings"
)

type lockedRawObject struct {
	path, digest string
	size         json.Number
}
type sourceSelection struct {
	url string
	raw lockedRawObject
}
type sourceArtifact struct{ record, platform *mapping }

type sourceLock struct {
	artifacts          map[string]sourceArtifact
	profiles, policies map[string]*mapping
	denied             []string
}

func selectSourceSnapshot(r *repository, id, version string) (sourceSelection, error) {
	lock, err := toolingAuthority(r, artifactLockPath)
	if err != nil {
		return sourceSelection{}, err
	}
	if recordErr := toolingRecord(r, lock, artifactLockPath, ""); recordErr != nil {
		return sourceSelection{}, recordErr
	}
	admission, err := toolingAuthority(r, artifactAdmissionPath)
	if err != nil {
		return sourceSelection{}, err
	}
	if recordErr := toolingRecord(r, admission, artifactAdmissionPath, ""); recordErr != nil {
		return sourceSelection{}, recordErr
	}
	profiles, err := toolingAuthority(r, artifactProfilesPath)
	if err != nil {
		return sourceSelection{}, err
	}
	selected, err := selectedSourceArtifacts(lock, id)
	if err != nil {
		return sourceSelection{}, err
	}
	policy, err := sourceLockPolicy(r, selected, profiles, admission)
	if err != nil {
		return sourceSelection{}, err
	}
	projected := mappingCopy(lock)
	entries := []any{}
	for _, name := range sortedSourceIDs(selected) {
		row := mappingCopy(selected[name].record)
		row.set("platforms", []any{selected[name].platform})
		entries = append(entries, row)
	}
	projected.set("artifacts", entries)
	if hasExecutableArtifactField(projected) || hasExecutableArtifactField(admission) {
		return sourceSelection{}, errArtifactSelection
	}
	if err := policy.validate(r); err != nil {
		return sourceSelection{}, err
	}
	target := selected[id]
	if target.record.get("version") != version || target.platform.get("platform_id") != "source-any" || !slices.Contains(stringSet(target.platform.get("profile_ids")), "source-snapshot") {
		return sourceSelection{}, errArtifactSelection
	}
	return boundSourceSelection(target)
}

func selectedSourceArtifacts(lock *mapping, id string) (map[string]sourceArtifact, error) {
	selected := map[string]sourceArtifact{}
	pending := []string{id}
	for len(pending) > 0 {
		name := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if _, seen := selected[name]; seen {
			continue
		}
		artifact, err := singleSourceArtifact(lock, name)
		if err != nil {
			return nil, err
		}
		selected[name] = artifact
		pending = append(pending, stringSet(artifact.platform.get("dependencies"))...)
	}
	return selected, nil
}

func singleSourceArtifact(lock *mapping, id string) (sourceArtifact, error) {
	matches := []*mapping{}
	for _, row := range mappingItems(lock.get("artifacts")) {
		if row.get("artifact_id") == id {
			matches = append(matches, row)
		}
	}
	if len(matches) != 1 {
		return sourceArtifact{}, errArtifactSelection
	}
	platforms := []*mapping{}
	for _, row := range mappingItems(matches[0].get("platforms")) {
		name, _ := row.get("platform_id").(string)
		if normalizeArtifactPlatform(name) == "source-any" {
			platforms = append(platforms, row)
		}
	}
	if len(platforms) != 1 {
		return sourceArtifact{}, errArtifactSelection
	}
	return sourceArtifact{matches[0], platforms[0]}, nil
}

func sortedSourceIDs(selected map[string]sourceArtifact) []string {
	ids := []string{}
	for id := range selected {
		ids = append(ids, id)
	}
	slices.Sort(ids)
	return ids
}

func sourceLockPolicy(r *repository, selected map[string]sourceArtifact, document, admission *mapping) (sourceLock, error) {
	profiles := map[string]*mapping{}
	ids := []string{}
	for _, row := range selected {
		ids = append(ids, stringSet(row.platform.get("profile_ids"))...)
	}
	slices.Sort(ids)
	ids = slices.Compact(ids)
	for _, id := range ids {
		matches := []*mapping{}
		for _, row := range mappingItems(document.get("profiles")) {
			if row.get("profile_id") == id {
				matches = append(matches, row)
			}
		}
		if len(matches) != 1 {
			return sourceLock{}, errArtifactSelection
		}
		if err := toolingRecord(r, matches[0], artifactProfilesPath, "artifactProfile"); err != nil {
			return sourceLock{}, err
		}
		profiles[id] = matches[0]
	}
	policies := map[string]*mapping{}
	for _, row := range mappingItems(admission.get("policies")) {
		name, _ := row.get("policy_id").(string)
		if policies[name] != nil {
			return sourceLock{}, errArtifactSelection
		}
		policies[name] = row
	}
	return sourceLock{selected, profiles, policies, stringSet(admission.get("denied_digests"))}, nil
}

func normalizeArtifactPlatform(value string) string {
	value = strings.ReplaceAll(strings.ToLower(strings.TrimFunc(value, pythonWhitespace)), "_", "-")
	parts := []string{}
	for part := range strings.SplitSeq(value, "-") {
		if part != "" {
			parts = append(parts, part)
		}
	}
	if len(parts) == 0 {
		return ""
	}
	if slices.Contains([]string{"darwin", "mac", "osx"}, parts[0]) {
		parts[0] = "macos"
	}
	if len(parts) > 1 {
		arch := strings.Join(parts[1:], "-")
		switch arch {
		case "64-bit", "amd64", "x64", "x86-64":
			arch = "x86-64"
		case "aarch64":
			arch = "arm64"
		}
		parts = []string{parts[0], arch}
	}
	return strings.ReplaceAll(strings.Join(parts, "-"), "x86-64", "x86_64")
}

func boundSourceSelection(row sourceArtifact) (sourceSelection, error) {
	urls, valid := stringList(row.platform.get("source_urls"), true)
	raws := mappingItems(row.platform.get("raw_manifest"))
	if !valid || len(urls) != 1 || len(raws) != 1 {
		return sourceSelection{}, errArtifactSelection
	}
	raw, err := lockedManifestObject(raws[0])
	if err != nil {
		return sourceSelection{}, err
	}
	return sourceSelection{urls[0], raw}, nil
}

func lockedManifestObject(raw *mapping) (lockedRawObject, error) {
	path, pathOK := raw.get("path").(string)
	digest, digestOK := raw.get("sha256").(string)
	size, sizeOK := raw.get("size").(json.Number)
	bytes, err := hex.DecodeString(digest)
	if !pathOK || !portableManifestPath(path) || !digestOK || err != nil || len(bytes) != 32 || strings.ToLower(digest) != digest || !sizeOK || strings.HasPrefix(string(size), "-") || size == "0" {
		return lockedRawObject{}, errArtifactSelection
	}
	return lockedRawObject{path, digest, size}, nil
}
func portableManifestPath(name string) bool {
	return name != "" && repositoryPath(name) && prefixPath(name) == name && !strings.Contains(name, `\`) && !manifestDrivePrefix(name)
}
