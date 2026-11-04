package admission

import (
	"io/fs"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) loadBehavioral(source fs.FS) error {
	e.relationCatalogs, e.relationProfiles = map[string]any{}, map[string]any{}
	current, err := readCatalog(source, "concept-authority/behavioral-relations-v1.json")
	if err != nil {
		return err
	}
	e.currentRelations = current
	e.relationCatalogs[stringAt(current, fieldTaxonomyRevision)] = current
	for _, revision := range []string{"rev8", "rev9", "rev10", "rev11", "rev12", "rev13"} {
		catalog, loadErr := readCatalog(source, "concept-authority/history/behavioral-relations-v1-"+revision+".json")
		if loadErr != nil {
			return loadErr
		}
		if stringAt(catalog, fieldTaxonomyRevision) != revision {
			return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
		}
		e.relationCatalogs[revision] = catalog
	}
	return e.loadRelationProfiles(source)
}

func (e *Validator) loadRelationProfiles(source fs.FS) error {
	for _, id := range []string{"participant-opacity-baseline-v1", "participant-opacity-runtime-reference-v1", "participant-opacity-theorem-v1", "participant-crossing-dpbb-finite-v1", "participant-crossing-multi-operation-dpbb-finite-v1"} {
		profile, loadErr := readCatalog(source, "profiles/behavioral-relation/"+id+".json")
		if loadErr != nil {
			return loadErr
		}
		if stringAt(profile, termProfileID) != id {
			return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
		}
		e.relationProfiles[join(id, stringAt(profile, "profile_revision"))] = profile
	}
	for _, historical := range [][3]string{
		{"participant-opacity-baseline-v1", "sem-231/rev2", "participant-opacity-baseline-v1-sem-231-rev2.json"},
		{"participant-opacity-runtime-reference-v1", "sem-231/runtime-rev1", "participant-opacity-runtime-reference-v1-sem-231-runtime-rev1.json"},
	} {
		profile, loadErr := readCatalog(source, "profiles/behavioral-relation/history/"+historical[2])
		if loadErr != nil {
			return loadErr
		}
		if stringAt(profile, termProfileID) != historical[0] || stringAt(profile, "profile_revision") != historical[1] {
			return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
		}
		e.relationProfiles[join(historical[0], historical[1])] = profile
	}
	return nil
}
func (e *Validator) behavioralRules() map[string]definition {
	return map[string]definition{
		"behavioral-relations-reference-resolution":           {check: behavioralCatalog},
		"behavioral-relation-profile-local-join":              {check: behavioralProfile},
		"behavioral-relation-profile-claim-resolution":        {check: e.profileClaim, contextual: true, requiresContext: true},
		"study-behavioral-claim-catalog-resolution":           {check: func(i validation.Invocation) error { return e.behavioralClaims(at(i.Instance, "behavioral_claims")) }},
		"scientific-completeness-behavioral-claim-resolution": {check: e.completenessClaims},
	}
}
func (e *Validator) behavioralClaims(claims any) error {
	if !unique(rowIDs(claims, fieldRelationID)) {
		return invalid()
	}
	for _, claim := range array(claims) {
		if err := e.behavioralClaim(claim, nil); err != nil {
			return err
		}
	}
	return nil
}
func (e *Validator) completenessClaims(i validation.Invocation) error {
	for _, profile := range array(at(i.Instance, "profiles")) {
		claims := at(profile, "behavioral_claims")
		if err := e.behavioralClaims(claims); err != nil {
			return err
		}
		nonclaimed := stringsOf(at(profile, "non_claimed_relation_ids"))
		if !subset(nonclaimed, keySet(at(e.currentRelations, "relations"))) || !disjoint(nonclaimed, rowSet(claims, fieldRelationID)) {
			return invalid()
		}
	}
	return nil
}
func (e *Validator) profileClaim(i validation.Invocation) error {
	context, ok := i.Context.(BehavioralClaimContext)
	if !ok {
		return contextRequired()
	}
	claim, err := e.low.DecodeObjectFragment("experiment-study-v1", "#/$defs/BehavioralClaimBindingModel", context.BehavioralClaim(), ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
	if err != nil {
		return invalid()
	}
	return e.behavioralClaim(claim, i.Instance)
}
func (e *Validator) behavioralClaim(claim, profile any) error {
	if err := claimStrength(claim); err != nil {
		return err
	}
	catalog := e.relationCatalogs[stringAt(claim, fieldTaxonomyRevision)]
	if catalog == nil || stringAt(claim, fieldTaxonomyID) != stringAt(catalog, fieldTaxonomyID) {
		return invalid()
	}
	relation := at(catalog, "relations", stringAt(claim, fieldRelationID))
	if relation == nil {
		return invalid()
	}
	if boolean(at(relation, "projection_required")) && at(claim, fieldObservationProjectionRef) == nil {
		return invalid()
	}
	if !boolean(at(relation, "relation_parameter_profile_required")) {
		return require(profile == nil)
	}
	if at(claim, "relation_parameter_profile_ref") == nil || at(claim, "assurance_axis") == nil {
		return invalid()
	}
	if profile == nil {
		profile = e.relationProfiles[join(stringAt(claim, "relation_parameter_profile_ref"), stringAt(claim, "relation_parameter_profile_revision"))]
	}
	if profile == nil {
		return invalid()
	}
	return claimProfile(claim, profile)
}
func claimProfile(claim, profile any) error {
	for profileField, claimField := range map[string]string{
		termProfileID: "relation_parameter_profile_ref", "profile_revision": "relation_parameter_profile_revision", fieldTaxonomyID: fieldTaxonomyID, fieldTaxonomyRevision: fieldTaxonomyRevision, fieldRelationID: fieldRelationID, fieldLeftCarrierRef: fieldLeftCarrierRef, fieldObservationProjectionRef: fieldObservationProjectionRef, fieldObservationProjectionRevision: fieldObservationProjectionRevision,
	} {
		if !equal(at(profile, profileField), at(claim, claimField)) {
			return invalid()
		}
	}
	kind := stringAt(profile, "parameters", termKind)
	if kind == crossingKind || kind == crossingMultiKind {
		return require(equal(at(claim, "right_carrier_ref"), at(profile, "parameters", "right", "model_id")))
	}
	return nil
}
