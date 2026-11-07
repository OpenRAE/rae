package concept

import (
	"cmp"
	"slices"
)

const currentStatus = "current"

type sourceTerm struct {
	TacticID   string `json:"tactic_id"`
	CategoryID string `json:"category_id"`
	ConceptID  string `json:"concept_id"`
}

type sourceWire struct {
	Authority     string       `json:"source_authority"`
	Version       string       `json:"source_version"`
	URL           string       `json:"source_url"`
	Digest        string       `json:"source_digest"`
	Tactics       []sourceTerm `json:"tactics"`
	Categories    []sourceTerm `json:"categories"`
	ActivityTypes []sourceTerm `json:"activity_types"`
	Acts          []sourceTerm `json:"communicative_acts"`
}

// pinnedSource adapts one packaged source catalog to its scheme.
type pinnedSource struct {
	path, scheme string
	terms        func(sourceWire) []string
}

func tactics(w sourceWire) []string {
	return termIDs(w.Tactics, func(t sourceTerm) string { return t.TacticID })
}

func termIDs(rows []sourceTerm, id func(sourceTerm) string) []string {
	ids := make([]string, 0, len(rows))
	for _, row := range rows {
		ids = append(ids, id(row))
	}
	return ids
}

// pinnedSources returns the five packaged sources and their schemes.
func pinnedSources() []pinnedSource {
	return []pinnedSource{
		{"concept-authority/attack-enterprise-tactics-source-v1.json", "mitre-attack-enterprise-tactics", tactics},
		{"concept-authority/atlas-tactics-source-v1.json", "mitre-atlas-tactics", tactics},
		{"concept-authority/nist-csf-defensive-categories-source-v1.json", "nist-csf-defensive-categories", func(w sourceWire) []string {
			return termIDs(w.Categories, func(t sourceTerm) string { return t.CategoryID })
		}},
		{"concept-authority/w3c-activitystreams-activity-types-source-v1.json", "w3c-activitystreams-activity-types", func(w sourceWire) []string {
			return termIDs(w.ActivityTypes, func(t sourceTerm) string { return t.ConceptID })
		}},
		{"concept-authority/fipa-communicative-acts-source-v1.json", "fipa-communicative-act-library", func(w sourceWire) []string {
			return termIDs(w.Acts, func(t sourceTerm) string { return t.ConceptID })
		}},
	}
}

// decodeSnapshots adapts each source. The adaptation keeps every source term,
// including a repeated one, so the resolver can report the ambiguity.
func (a *Authority) decodeSnapshots(documents map[string][]byte) error {
	for _, source := range pinnedSources() {
		var wire sourceWire
		if err := decode(documents[source.path], &wire); err != nil {
			return err
		}
		snapshot := SchemeSnapshot{SchemeID: source.scheme, Authority: wire.Authority, Revision: wire.Version, SourceLocator: wire.URL, SourceDigest: wire.Digest}
		for _, id := range source.terms(wire) {
			snapshot.Concepts = append(snapshot.Concepts, SnapshotTerm{ConceptID: id, Status: currentStatus})
		}
		if checkSnapshot(snapshot) != nil {
			return damaged()
		}
		a.snapshots = append(a.snapshots, snapshot)
	}
	slices.SortFunc(a.snapshots, func(x, y SchemeSnapshot) int { return cmp.Compare(x.SchemeID, y.SchemeID) })
	return nil
}

// PinnedSnapshots adapts the five packaged source snapshots in scheme ID
// order.
func (a *Authority) PinnedSnapshots() []SchemeSnapshot {
	snapshots := slices.Clone(a.snapshots)
	for i := range snapshots {
		snapshots[i] = snapshots[i].copy()
	}
	return snapshots
}

func (s SchemeSnapshot) copy() SchemeSnapshot {
	s.Concepts = slices.Clone(s.Concepts)
	for i := range s.Concepts {
		s.Concepts[i].SuccessorConceptIDs = slices.Clone(s.Concepts[i].SuccessorConceptIDs)
	}
	return s
}
