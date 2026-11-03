package admission

func (e *Validator) flowProfileDocument(id string, root any) error {
	v, err := e.defaulted(id, root)
	if err != nil {
		return err
	}
	digest, err := jsonDigest(v)
	if err != nil {
		return err
	}
	pin := map[string]string{
		"participant-boundary-flow-policy-v1": "sha256:43546386e7c7331fd6ce4b42195b2446d984cf14d1a90aa8f050ef8166d01801",
		termParticipantOwnerFlowPolicyV1:      "sha256:0a7872665ca0cf435bddcd0d6a39b89d20a8f5f6a5e8ca8abdf1d4f77da774df",
	}[id]
	return require(pin != "" && digest == pin)
}
