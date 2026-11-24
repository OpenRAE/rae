package admission

import (
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

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
		current := map[string]bool{}
		for _, relation := range e.authority.CurrentRelationCatalog().Relations {
			current[relation.ID] = true
		}
		if !subset(nonclaimed, current) || !disjoint(nonclaimed, rowSet(claims, fieldRelationID)) {
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

// behavioralClaim applies the claim model rules, then resolves the claim
// through the profile owner. A supplied profile is the document under
// admission.
func (e *Validator) behavioralClaim(claim, supplied any) error {
	if err := claimStrength(claim); err != nil {
		return err
	}
	var profileRecord *profile.RelationProfile
	if supplied != nil {
		profileRecord = relationProfileRecord(supplied)
	}
	return require(e.owners.CheckBehavioralClaim(e.authority, behavioralClaimRecord(claim), profileRecord) == nil)
}

func behavioralClaimRecord(claim any) profile.BehavioralClaim {
	return profile.BehavioralClaim{
		TaxonomyID: stringAt(claim, fieldTaxonomyID), TaxonomyRevision: stringAt(claim, fieldTaxonomyRevision), RelationID: stringAt(claim, fieldRelationID),
		LeftCarrierRef: stringAt(claim, fieldLeftCarrierRef), RightCarrierRef: stringAt(claim, "right_carrier_ref"),
		ObservationProjectionRef: stringAt(claim, fieldObservationProjectionRef), ObservationProjectionRevision: stringAt(claim, fieldObservationProjectionRevision),
		ProfileRef: stringAt(claim, "relation_parameter_profile_ref"), ProfileRevision: stringAt(claim, "relation_parameter_profile_revision"), AssuranceAxis: stringAt(claim, "assurance_axis"),
	}
}

func relationProfileRecord(v any) *profile.RelationProfile {
	record := profile.RelationProfile{
		ID: stringAt(v, termProfileID), Revision: stringAt(v, "profile_revision"), TaxonomyID: stringAt(v, fieldTaxonomyID), TaxonomyRevision: stringAt(v, fieldTaxonomyRevision),
		RelationID: stringAt(v, fieldRelationID), ParameterKind: stringAt(v, "parameters", termKind), LeftCarrierRef: stringAt(v, fieldLeftCarrierRef),
		ObservationProjectionRef: stringAt(v, fieldObservationProjectionRef), ObservationProjectionRevision: stringAt(v, fieldObservationProjectionRevision),
	}
	if record.ParameterKind == crossingKind || record.ParameterKind == crossingMultiKind {
		record.RightCarrierRef = stringAt(v, "parameters", "right", "model_id")
	}
	return &record
}
