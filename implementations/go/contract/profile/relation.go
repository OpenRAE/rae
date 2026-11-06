package profile

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/concept"
)

// MaxRelationProfileBytes is the reference size limit of one
// behavioral-relation profile document.
const MaxRelationProfileBytes = 256 << 10

// The parameter kinds of the participant-crossing profiles. Only these kinds
// name a right carrier.
const (
	CrossingKind      = "participant-crossing-dpbb/v1"
	CrossingMultiKind = "participant-crossing-multi-dpbb/v1"
)

// RelationProfile is one exact revision of a behavioral-relation profile.
// RightCarrierRef is set only for the participant-crossing parameter kinds.
type RelationProfile struct {
	ID, Revision, TaxonomyID, TaxonomyRevision, RelationID  string
	ParameterKind, LeftCarrierRef, RightCarrierRef          string
	ObservationProjectionRef, ObservationProjectionRevision string
}

// BehavioralClaim is the part of a behavioral claim binding that joins the
// taxonomy and the relation profile. An empty optional field is absent.
type BehavioralClaim struct {
	TaxonomyID, TaxonomyRevision, RelationID                string
	LeftCarrierRef, RightCarrierRef                         string
	ObservationProjectionRef, ObservationProjectionRevision string
	ProfileRef, ProfileRevision, AssuranceAxis              string
}

// relationProfileIDs returns the supported profile IDs in order.
func relationProfileIDs() []string {
	return []string{
		"participant-crossing-dpbb-finite-v1",
		"participant-crossing-multi-operation-dpbb-finite-v1",
		"participant-opacity-baseline-v1",
		"participant-opacity-runtime-reference-v1",
		"participant-opacity-theorem-v1",
	}
}

type historyEntry struct{ id, revision, path string }

// relationHistory registers each history revision and its file.
func relationHistory() []historyEntry {
	return []historyEntry{
		{"participant-opacity-baseline-v1", "sem-231/rev2", relationDir + "history/participant-opacity-baseline-v1-sem-231-rev2.json"},
		{"participant-opacity-runtime-reference-v1", "sem-231/runtime-rev1", relationDir + "history/participant-opacity-runtime-reference-v1-sem-231-runtime-rev1.json"},
	}
}

// portableIdentifier reports the portable local identifier grammar: a
// lowercase ASCII letter or digit, then up to 63 of those, '_' or '-'.
func portableIdentifier(id string) bool {
	if id == "" || len(id) > 64 || id[0] == '_' || id[0] == '-' {
		return false
	}
	return strings.Trim(id, "abcdefghijklmnopqrstuvwxyz0123456789_-") == ""
}

type relationWire struct {
	ProfileID                     string `json:"profile_id"`
	ProfileRevision               string `json:"profile_revision"`
	TaxonomyID                    string `json:"taxonomy_id"`
	TaxonomyRevision              string `json:"taxonomy_revision"`
	RelationID                    string `json:"relation_id"`
	LeftCarrierRef                string `json:"left_carrier_ref"`
	ObservationProjectionRef      string `json:"observation_projection_ref"`
	ObservationProjectionRevision string `json:"observation_projection_revision"`
	Parameters                    struct {
		Kind  string `json:"kind"`
		Right struct {
			ModelID string `json:"model_id"`
		} `json:"right"`
	} `json:"parameters"`
}

func decodeRelationProfile(data []byte) (RelationProfile, error) {
	var wire relationWire
	if err := decode(data, &wire); err != nil {
		return RelationProfile{}, err
	}
	profile := RelationProfile{ID: wire.ProfileID, Revision: wire.ProfileRevision, TaxonomyID: wire.TaxonomyID, TaxonomyRevision: wire.TaxonomyRevision, RelationID: wire.RelationID, ParameterKind: wire.Parameters.Kind, LeftCarrierRef: wire.LeftCarrierRef, ObservationProjectionRef: wire.ObservationProjectionRef, ObservationProjectionRevision: wire.ObservationProjectionRevision}
	if profile.ParameterKind == CrossingKind || profile.ParameterKind == CrossingMultiKind {
		profile.RightCarrierRef = wire.Parameters.Right.ModelID
	}
	return profile, nil
}

// decodeRelations keys each packaged profile by its exact identity. A file
// must hold the profile of its registry entry.
func (p *Profiles) decodeRelations(documents map[string][]byte) error {
	p.relations = map[[2]string]RelationProfile{}
	add := func(id, revision, path string) error {
		if len(documents[path]) > MaxRelationProfileBytes {
			return damaged()
		}
		profile, err := decodeRelationProfile(documents[path])
		if err != nil {
			return err
		}
		key := [2]string{profile.ID, profile.Revision}
		if _, repeated := p.relations[key]; repeated || profile.ID != id || revision != "" && profile.Revision != revision {
			return damaged()
		}
		p.relations[key] = profile
		return nil
	}
	for _, id := range relationProfileIDs() {
		if err := add(id, "", relationDir+id+".json"); err != nil {
			return err
		}
	}
	for _, entry := range relationHistory() {
		if err := add(entry.id, entry.revision, entry.path); err != nil {
			return err
		}
	}
	return nil
}

// RelationProfileIDs returns the supported profile IDs in order.
func (p *Profiles) RelationProfileIDs() []string { return relationProfileIDs() }

// RelationProfile returns the packaged profile of the exact revision. An
// unsupported ID or revision is a NotFound fault.
func (p *Profiles) RelationProfile(id, revision string) (RelationProfile, error) {
	if !portableIdentifier(id) || !slices.Contains(relationProfileIDs(), id) {
		return RelationProfile{}, notFound("behavioral-authority-unsupported")
	}
	profile, ok := p.relations[[2]string{id, revision}]
	if !ok {
		return RelationProfile{}, notFound("behavioral-authority-unsupported")
	}
	return profile, nil
}

// CheckBehavioralClaim resolves the claim against its exact taxonomy revision
// and, when the relation requires one, its exact profile revision. A supplied
// profile replaces the packaged lookup; it is refused for a relation that
// requires no profile. A claim that does not join is an InvalidInput fault.
func (p *Profiles) CheckBehavioralClaim(authority *concept.Authority, claim BehavioralClaim, supplied *RelationProfile) error {
	catalog, err := authority.RelationCatalog(claim.TaxonomyRevision)
	if err != nil || claim.TaxonomyID != catalog.TaxonomyID {
		return claimMismatch()
	}
	relation, ok := catalog.Relation(claim.RelationID)
	if !ok || relation.ProjectionRequired && claim.ObservationProjectionRef == "" {
		return claimMismatch()
	}
	if !relation.ProfileRequired {
		if supplied != nil {
			return claimMismatch()
		}
		return nil
	}
	if claim.ProfileRef == "" || claim.AssuranceAxis == "" {
		return claimMismatch()
	}
	profile := supplied
	if profile == nil {
		packaged, err := p.RelationProfile(claim.ProfileRef, claim.ProfileRevision)
		if err != nil {
			return claimMismatch()
		}
		profile = &packaged
	}
	return joinProfile(claim, catalog, *profile)
}

func joinProfile(claim BehavioralClaim, catalog concept.RelationCatalog, profile RelationProfile) error {
	crossing := profile.ParameterKind == CrossingKind || profile.ParameterKind == CrossingMultiKind
	if crossing && claim.RightCarrierRef != profile.RightCarrierRef {
		return claimMismatch()
	}
	pairs := [][2]string{
		{profile.ID, claim.ProfileRef},
		{profile.Revision, claim.ProfileRevision},
		{profile.TaxonomyID, claim.TaxonomyID},
		{profile.TaxonomyRevision, claim.TaxonomyRevision},
		{profile.TaxonomyID, catalog.TaxonomyID},
		{profile.TaxonomyRevision, catalog.TaxonomyRevision},
		{profile.RelationID, claim.RelationID},
		{profile.LeftCarrierRef, claim.LeftCarrierRef},
		{profile.ObservationProjectionRef, claim.ObservationProjectionRef},
		{profile.ObservationProjectionRevision, claim.ObservationProjectionRevision},
	}
	for _, pair := range pairs {
		if pair[0] != pair[1] {
			return claimMismatch()
		}
	}
	return nil
}

func claimMismatch() error { return invalid("behavioral-claim-mismatch") }
