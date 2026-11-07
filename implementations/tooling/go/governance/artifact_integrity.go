package governance

import (
	"crypto/sha256"
	"fmt"
	"slices"
	"strings"
)

func (s sourceLock) validate(r *repository) error {
	if sourceDependencyCycle(s.artifacts) {
		return errArtifactSelection
	}
	for _, id := range sortedSourceIDs(s.artifacts) {
		if err := s.validateSource(r, id, s.artifacts[id]); err != nil {
			return err
		}
	}
	return nil
}

func (s sourceLock) validateSource(r *repository, id string, row sourceArtifact) error {
	if row.record.get("artifact_class") != "source-snapshot" {
		return artifactPolicyError("native vocabulary acquisition requires a source-snapshot selection")
	}
	if mutableArtifactSelector(row.record.get("version")) || mutableArtifactSelector(object(row.record.get("source")).get("release")) {
		return errArtifactSelection
	}
	authenticity := object(row.record.get("authenticity")).get("status")
	if authenticity != "verified" && authenticity != "absent-reviewed" {
		return errArtifactSelection
	}
	source := object(row.record.get("source"))
	repository, _ := source.get("repository").(string)
	if secretArtifactLocator(repository) {
		return errArtifactSelection
	}
	provided := []string{"raw-sha256", "exact-size", "installed-sha256", "checked-in-byte-sha256", "incumbent-source-digest"}
	if authenticity == "absent-reviewed" {
		provided = append(provided, "absent-signature-review")
	}
	if err := s.sourcePolicyJoin(row.record, provided); err != nil {
		return err
	}
	return s.validateSourcePlatform(r, id, row, source)
}

func (s sourceLock) sourcePolicyJoin(artifact *mapping, provided []string) error {
	refs := stringSet(artifact.get("policy_refs"))
	if len(refs) == 0 {
		return errArtifactSelection
	}
	allGraphPolicies := true
	for _, ref := range refs {
		policy := s.policies[ref]
		if policy == nil || policy.get("status") != "active" || policy.get("subject") != "source-snapshot" {
			return errArtifactSelection
		}
		accepted := stringSet(policy.get("accepted_evidence"))
		for _, evidence := range provided {
			if !slices.Contains(accepted, evidence) {
				return errArtifactSelection
			}
		}
		allGraphPolicies = allGraphPolicies && slices.Contains(accepted, "oci-platform-graph-digests")
	}
	if allGraphPolicies {
		return errArtifactSelection
	}
	return nil
}

func (s sourceLock) validateSourcePlatform(r *repository, id string, row sourceArtifact, source *mapping) error {
	platform := row.platform
	if platform.get("installed_tree") != nil || platform.get("oci_graph") != nil || platform.get("installed_identity") != nil {
		return artifactPolicyError("native vocabulary acquisition does not admit installation or OCI selections")
	}
	urls, _ := stringList(platform.get("source_urls"), true)
	locators := stringSet(source.get("locator_refs"))
	ordered, _ := source.get("locator_refs").([]any)
	if len(urls) != len(ordered) {
		return errArtifactSelection
	}
	if slices.ContainsFunc(urls, secretArtifactLocator) {
		return errArtifactSelection
	}
	platformName, _ := platform.get("platform_id").(string)
	for _, profileID := range stringSet(platform.get("profile_ids")) {
		if !sourceProfileMatches(s.profiles[profileID], id, normalizeArtifactPlatform(platformName), locators) {
			return errArtifactSelection
		}
	}
	if len(mappingItems(platform.get("installed_manifest"))) == 0 {
		return errArtifactSelection
	}
	if err := s.validateManifest(r, platform.get("raw_manifest"), false); err != nil {
		return err
	}
	return s.validateManifest(r, platform.get("installed_manifest"), true)
}

func (s sourceLock) validateManifest(r *repository, value any, installed bool) error {
	for _, entry := range mappingItems(value) {
		locked, err := lockedManifestObject(entry)
		if err != nil {
			return err
		}
		if slices.Contains(s.denied, locked.digest) {
			return errArtifactSelection
		}
		if installed {
			if verifyErr := verifyInstalledSnapshot(r, locked); verifyErr != nil {
				return verifyErr
			}
		}
	}
	return nil
}

func sourceProfileMatches(profile *mapping, id, platform string, locators []string) bool {
	if profile == nil {
		return false
	}
	value := object(profile.get("platform"))
	canonical, _ := value.get("canonical_id").(string)
	if normalizeArtifactPlatform(canonical) != platform || !slices.Contains(stringSet(profile.get("supported_artifact_ids")), id) {
		return false
	}
	for _, alias := range stringSet(value.get("aliases")) {
		if normalizeArtifactPlatform(alias) != normalizeArtifactPlatform(canonical) {
			return false
		}
	}
	admitted := []string{}
	for _, entry := range mappingItems(profile.get("locator_classes")) {
		if name, ok := entry.get("locator_id").(string); ok {
			admitted = append(admitted, name)
		}
	}
	for _, locator := range locators {
		if !slices.Contains(admitted, locator) {
			return false
		}
	}
	return true
}

func verifyInstalledSnapshot(r *repository, locked lockedRawObject) error {
	if !regularRepoFile(r, locked.path) {
		return errArtifactSelection
	}
	bytes, err := r.readLimit(locked.path, toolingAuthorityLimit)
	if err != nil {
		return errArtifactSelection
	}
	size, err := locked.size.Int64()
	if err != nil || int64(len(bytes)) != size || fmt.Sprintf("%x", sha256.Sum256(bytes)) != locked.digest {
		return errArtifactSelection
	}
	return nil
}

func mutableArtifactSelector(raw any) bool {
	text, ok := raw.(string)
	if !ok {
		return false
	}
	text = strings.ToLower(text)
	return strings.HasPrefix(text, "refs/heads/") || slices.Contains([]string{"dev", "head", "latest", "main", "master", "nightly", "stable"}, text)
}

func sourceDependencyCycle(artifacts map[string]sourceArtifact) bool {
	counts := map[string]int{}
	for id := range artifacts {
		counts[id] = 0
	}
	for _, row := range artifacts {
		for _, dependency := range stringSet(row.platform.get("dependencies")) {
			counts[dependency]++
		}
	}
	pending := []string{}
	for id, count := range counts {
		if count == 0 {
			pending = append(pending, id)
		}
	}
	visited := 0
	for len(pending) > 0 {
		id := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		visited++
		for _, dependency := range stringSet(artifacts[id].platform.get("dependencies")) {
			counts[dependency]--
			if counts[dependency] == 0 {
				pending = append(pending, dependency)
			}
		}
	}
	return visited != len(artifacts)
}
