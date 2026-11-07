package governance

import (
	"io/fs"
	"path"
	"slices"
	"strings"
)

const authorityOverlapRule = "categorisation-overlap"
const authorityEntryID = "' (id="
const authorityRootPrefix = "authority root '"

func boundaryOverlap(normative, consumers []boundaryRoot, legacy []string) []Finding {
	findings := []Finding{}
	for _, a := range normative {
		for _, b := range consumers {
			if a.root == b.root {
				findings = append(findings, boundaryFailure(authorityOverlapRule, "root '"+a.root+"' is classified as both authority (id="+pythonRepr(a.id)+") and non-normative (id="+pythonRepr(b.id)+"); each root must have exactly one classification"))
			}
		}
	}
	findings = append(findings, boundaryLegacyOverlap(normative, consumers, legacy)...)
	return append(findings, boundaryAncestorOverlap(normative, consumers)...)
}
func boundaryLegacyOverlap(normative, consumers []boundaryRoot, legacy []string) []Finding {
	findings := []Finding{}
	for _, group := range []struct {
		label string
		roots []boundaryRoot
	}{{authorityField, normative}, {"non-normative", consumers}} {
		for _, entry := range group.roots {
			first := boundaryFirstPart(entry.root)
			if first != "" && slices.Contains(legacy, first) {
				findings = append(findings, boundaryFailure(authorityOverlapRule, group.label+" root '"+entry.root+authorityEntryID+pythonRepr(entry.id)+") shares its top-level segment '"+first+"' with legacy_top_level_dirs; legacy dirs must remain absent and may not host a classified root"))
			}
		}
	}
	return findings
}
func boundaryAncestorOverlap(normative, consumers []boundaryRoot) []Finding {
	findings := []Finding{}
	for _, a := range normative {
		for _, b := range consumers {
			if a.root == b.root {
				continue
			}
			if strings.HasPrefix(b.root, a.root) {
				findings = append(findings, boundaryFailure(authorityOverlapRule, authorityRootPrefix+a.root+authorityEntryID+pythonRepr(a.id)+") is an ancestor of non-normative root '"+b.root+authorityEntryID+pythonRepr(b.id)+"); a child of a normative root cannot be non-normative"))
			} else if strings.HasPrefix(a.root, b.root) {
				findings = append(findings, boundaryFailure(authorityOverlapRule, "non-normative root '"+b.root+authorityEntryID+pythonRepr(b.id)+") is an ancestor of authority root '"+a.root+authorityEntryID+pythonRepr(a.id)+"); a child of a non-normative root cannot be authority"))
			}
		}
	}
	return findings
}

func boundaryFirstPart(name string) string {
	for part := range strings.SplitSeq(name, "/") {
		if part != "" && part != "." {
			return part
		}
	}
	return ""
}

func boundaryDisk(r *repository, normative, consumers []boundaryRoot, legacy []string) ([]Finding, error) {
	findings := []Finding{}
	for _, entry := range normative {
		if !boundaryDirectory(r, entry.root) {
			findings = append(findings, finding("authority-boundary-root-missing", authorityRootPrefix+entry.root+authorityEntryID+pythonRepr(entry.id)+") does not exist on disk", entry.root))
			continue
		}
		entries, err := boundaryDirectoryEntries(r, entry.root)
		if err != nil {
			return nil, err
		}
		if !slices.ContainsFunc(entries, func(child fs.DirEntry) bool { return child.Name() != ".keep" }) {
			findings = append(findings, finding("authority-boundary-root-empty", authorityRootPrefix+entry.root+authorityEntryID+pythonRepr(entry.id)+") exists but contains no artifacts", entry.root))
		}
	}
	remaining, err := boundaryOtherDirectories(r, normative, consumers, legacy)
	return append(findings, remaining...), err
}
func boundaryOtherDirectories(r *repository, normative, consumers []boundaryRoot, legacy []string) ([]Finding, error) {
	findings := []Finding{}
	for _, name := range legacy {
		if boundaryDirectory(r, name) {
			findings = append(findings, finding("authority-boundary-legacy-dir-present", "legacy top-level directory '"+name+"' must not exist (ADR-009: transitional paths have been migrated and may not reappear)", name))
		}
	}
	classified := slices.Clone(legacy)
	for _, entry := range append(slices.Clone(normative), consumers...) {
		classified = append(classified, boundaryFirstPart(entry.root))
	}
	children, err := fs.ReadDir(r.root.FS(), ".")
	if err != nil {
		return nil, err
	}
	for _, child := range children {
		if !child.IsDir() || boundaryPruned(child.Name()) || slices.Contains(classified, child.Name()) {
			continue
		}
		findings = append(findings, finding("authority-boundary-unclassified-top-level", "top-level directory '"+child.Name()+"' is not classified in authority_roots, non_normative_roots, or legacy_top_level_dirs", child.Name()))
	}
	return findings, nil
}
func boundaryDirectory(r *repository, name string) bool {
	resolved, err := r.resolve(name)
	if err != nil {
		return false
	}
	info, err := r.root.Stat(path.Clean(resolved))
	return err == nil && info.IsDir()
}
