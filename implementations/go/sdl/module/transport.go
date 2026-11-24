package module

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
)

// Resolve selects and verifies an OCI module using only configured registries.
func (r *Registry) Resolve(ctx context.Context, source, version, pin string) (*Bundle, error) {
	return r.resolve(ctx, source, version, pin, nil)
}
func (r *Registry) resolve(ctx context.Context, source, version, pin string, locked *LockRecord) (*Bundle, error) {
	registry, repository, err := ociSource(source)
	if err != nil || r == nil {
		return nil, invalid()
	}
	rule, allowed := r.policy.Registries[registry]
	if !allowed {
		return nil, invalid()
	}
	requirement, pin, err := moduleRequest(version, pin)
	if err != nil {
		return nil, err
	}
	scheme := "https"
	if rule.AllowInsecureHTTP || strings.HasPrefix(registry, "localhost:") || strings.HasPrefix(registry, "127.0.0.1:") {
		scheme = "http"
	}
	base := scheme + "://" + registry + "/v2/" + escapeRepository(repository)
	bounded, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	client, transport, err := registryClient(scheme, registry)
	if err != nil {
		return nil, err
	}
	defer transport.CloseIdleConnections()
	manifestReference, err := r.resolveManifestReference(bounded, client, base, requirement, locked)
	if err != nil {
		return nil, err
	}
	artifact, err := r.fetchArtifact(bounded, client, base, manifestReference, locked)
	if err != nil {
		return nil, err
	}
	requested := LockRecord{Source: source, RequestedVersion: version, ResolvedSource: registry + "/" + repository + "@" + digest.SHA256(artifact.Manifest)}
	if requested.RequestedVersion == "" {
		requested.RequestedVersion = "*"
	}
	return r.verify(bounded, registry, artifact, requested, &resolutionConstraints{version: requirement, pin: pin, locked: locked})
}

type resolutionConstraints struct {
	version versionRequirement
	pin     string
	locked  *LockRecord
}

func resolvedModuleMatches(record LockRecord, requirement versionRequirement, pin string, locked *LockRecord) bool {
	return requirement.accepts(record.ModuleVersion) && (pin == "" || pin == record.ContentDigest) && (locked == nil || locked.ModuleID == record.ModuleID && locked.ExportHash == record.ExportHash)
}
func moduleRequest(version, pin string) (versionRequirement, string, error) {
	if len(pin) == 64 {
		pin = "sha256:" + pin
	}
	if pin != "" && !digest.Valid(pin) {
		return versionRequirement{}, "", invalid()
	}
	requirement, err := versionSpec(version)
	return requirement, pin, err
}
func (r *Registry) fetchArtifact(ctx context.Context, client *http.Client, base, manifestReference string, locked *LockRecord) (Artifact, error) {
	manifestBytes, err := fetch(ctx, client, base+"/manifests/"+url.PathEscape(manifestReference), r.limits.metadataBytes)
	if err != nil {
		return Artifact{}, err
	}
	if locked != nil && locked.ManifestDigest != digest.SHA256(manifestBytes) {
		return Artifact{}, invalid()
	}
	manifest, layer, err := r.readManifest(manifestBytes)
	if err != nil {
		return Artifact{}, err
	}
	configBytes, err := fetch(ctx, client, base+"/blobs/"+url.PathEscape(manifest.Config.Digest), r.limits.metadataBytes)
	if err != nil {
		return Artifact{}, err
	}
	if digest.SHA256(configBytes) != manifest.Config.Digest {
		return Artifact{}, invalid()
	}
	bundleBytes, err := fetch(ctx, client, base+"/blobs/"+url.PathEscape(layer.Digest), r.limits.bundleBytes)
	if err != nil {
		return Artifact{}, err
	}
	return Artifact{Manifest: manifestBytes, Config: configBytes, Bundle: bundleBytes}, nil
}
func (r *Registry) resolveManifestReference(ctx context.Context, client *http.Client, base string, requirement versionRequirement, locked *LockRecord) (string, error) {
	if locked != nil {
		if !digest.Valid(locked.ManifestDigest) {
			return "", invalid()
		}
		return locked.ManifestDigest, nil
	}
	raw, err := fetch(ctx, client, base+"/tags/list", r.limits.metadataBytes)
	if err != nil {
		return "", err
	}
	var payload struct {
		Tags []string `json:"tags"`
	}
	if json.Unmarshal(raw, &payload) != nil {
		return "", invalid()
	}
	return selectTag(payload.Tags, requirement)
}
func registryClient(scheme, registry string) (*http.Client, *http.Transport, error) {
	standard, ok := http.DefaultTransport.(*http.Transport)
	if !ok {
		return nil, nil, invalid()
	}
	transport := standard.Clone()
	transport.Proxy = nil

	client := &http.Client{Transport: transport, Timeout: 30 * time.Second, CheckRedirect: func(request *http.Request, via []*http.Request) error {
		if len(via) >= 10 || request.URL.Scheme != scheme || request.URL.Host != registry {
			return invalid()
		}
		return nil
	}}
	return client, transport, nil
}
func ociSource(source string) (string, string, error) {
	value, ok := strings.CutPrefix(source, "oci:")
	if !ok {
		return "", "", invalid()
	}
	if before, after, qualified := strings.Cut(value, "://"); qualified {
		if before != "http" && before != "https" {
			return "", "", invalid()
		}
		value = after
	}
	registry, repository, present := strings.Cut(value, "/")
	if !present || registry == "" || repository == "" || strings.ContainsAny(value, "?#@\\\x00%") {
		return "", "", invalid()
	}
	parsed, err := url.Parse("https://" + registry)
	if err != nil || parsed.Host != registry || parsed.User != nil || parsed.Hostname() == "" {
		return "", "", invalid()
	}
	for part := range strings.SplitSeq(repository, "/") {
		if part == "" || part == "." || part == ".." {
			return "", "", invalid()
		}
	}
	return registry, repository, nil
}
func escapeRepository(repository string) string {
	parts := strings.Split(repository, "/")
	for index, part := range parts {
		parts[index] = url.PathEscape(part)
	}
	return strings.Join(parts, "/")
}
func fetch(ctx context.Context, client *http.Client, address string, limit int64) ([]byte, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, address, nil)
	if err != nil {
		return nil, invalid()
	}
	request.Header.Set("Accept", manifestMediaType)
	response, err := client.Do(request)
	if err != nil {
		return nil, operational(err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode < 200 || response.StatusCode >= 300 || response.ContentLength > limit {
		return nil, invalid()
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, limit+1))
	if err != nil {
		return nil, operational(err)
	}
	if int64(len(raw)) > limit {
		return nil, invalid()
	}
	return raw, nil
}
func selectTag(tags []string, requirement versionRequirement) (string, error) {
	var best pepVersion
	selected := ""
	for _, tag := range tags {
		version, status := parsePEP(tag)
		if status != versionValid || !requirement.accepts(tag) {
			continue
		}
		order := version.compare(best, true)
		if selected == "" || order > 0 || order == 0 && tag > selected {
			best = version
			selected = tag
		}
	}
	if selected != "" {
		return selected, nil
	}
	if requirement.unrestricted {
		selected = largestOpaqueTag(tags)
	}

	if selected == "" {
		return "", invalid()
	}
	return selected, nil
}

func largestOpaqueTag(tags []string) string {
	selected := ""
	for _, tag := range tags {
		if tag > selected {
			selected = tag
		}
	}
	return selected
}
