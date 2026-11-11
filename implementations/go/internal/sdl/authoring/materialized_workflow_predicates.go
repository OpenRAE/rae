package authoring

func workflowOutcomes(kind string) []string {
	switch kind {
	case objectiveStep, callStep, parallelStepType:
		return []string{"succeeded", termFailed}
	case retryStep:
		return []string{"succeeded", "exhausted"}
	default:
		return nil
	}
}
