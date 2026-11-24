package admission

import "github.com/OpenRAE/rae/implementations/go/base/fault"

func (e *Validator) loadControlProfiles(documents map[string][]byte) error {
	e.controlDigests = map[string]string{}
	for id, path := range map[string]string{
		termTeachingInfluence:               "profiles/participant-control/teaching-influence-rev1.json",
		termParticipantBoundaryFlowPolicyV1: "profiles/participant-boundary-flow-policy/participant-boundary-flow-policy-v1.json",
		termParticipantOwnerFlowPolicyV1:    "profiles/participant-boundary-flow-policy/participant-owner-flow-policy-v1.json",
	} {
		profile, err := parseCatalog(documents[path])
		if err != nil {
			return err
		}
		digest, err := jsonDigest(profile)
		if err != nil {
			return fault.New(fault.Operational, codeContractCatalogInvalid, nil)
		}
		e.controlDigests[id] = digest
	}
	return nil
}
func (e *Validator) controlProfile(v any) error {
	digest, known := e.controlDigests[stringAt(v, "ref")]
	return require(known && stringAt(v, termKind) == termProfile && stringAt(v, termRevision) == termRev1 && stringAt(v, termDigest) == digest)
}
