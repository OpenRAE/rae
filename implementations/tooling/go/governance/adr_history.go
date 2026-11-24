package governance

import (
	"context"
	"slices"
	"strings"
)

func (c *checker) adrBase(ctx context.Context, r *repository) (string, []Finding, error) {
	if c.request.Staged {
		return "HEAD", nil, nil
	}
	var data []byte
	var err error
	if validRevision(c.request.BaseRevision) {
		data, err = gitOptional(ctx, r, "", "rev-parse", "--verify", "--quiet", "--end-of-options", c.request.BaseRevision+"^{commit}")
	}
	if err != nil {
		return "", nil, err
	}
	if len(data) == 0 {
		return "", []Finding{finding("adr-base-rev-unresolved", "--base-rev "+pythonRepr(c.request.BaseRevision)+" does not name a commit in this repository, so no accepted ADR can be compared against its base; fetch the base or pass a valid revision", "")}, nil
	}
	return strings.TrimSpace(string(data)), nil, nil
}

func (c *checker) adrEdits(ctx context.Context, r *repository, documents []adrDocument) ([]Finding, error) {
	base, findings, err := c.adrBase(ctx, r)
	if err != nil || len(findings) > 0 {
		return findings, err
	}
	paths, err := adrBasePaths(ctx, r, base)
	if err != nil {
		return nil, err
	}
	for _, doc := range documents {
		before, err := adrBaseCopy(ctx, r, base, paths[doc.id], doc.path)
		if err != nil {
			return nil, err
		}
		if before == nil {
			continue
		}
		after := []byte(doc.text)
		if c.request.Staged {
			after, err = gitBlob(ctx, r, ":"+doc.path, false)
			if err != nil {
				return nil, err
			}
		}
		if unrecordedADREdit(before, after) {
			findings = append(findings, finding("adr-amendment-unrecorded", doc.id+": accepted ADR content changed without a new ## Amendments record; add an amendment (and update its pin) or supersede it with a new ADR", doc.path))
		}
	}
	return findings, nil
}

func adrBaseCopy(ctx context.Context, r *repository, base, recorded, current string) ([]byte, error) {
	if recorded == "" {
		recorded = current
	}
	for _, name := range []string{recorded, current} {
		data, err := gitBlob(ctx, r, base+":"+name, true)
		if err != nil || data != nil {
			return data, err
		}
	}
	return nil, nil
}

func unrecordedADREdit(before, after []byte) bool {
	if after == nil || adrHash(string(before)) == adrHash(string(after)) {
		return false
	}
	old := amendmentRefs(string(before))
	for _, ref := range amendmentRefs(string(after)) {
		if !slices.Contains(old, ref) {
			return false
		}
	}
	return true
}
