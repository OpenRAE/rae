package authoring

const (
	variationParameterKind   = "parameter"
	variationAlternativeKind = "alternative"
	variationNumericKind     = "numeric-interval"
	variationSecondsUnit     = "seconds"
)

func variationReferenceSlot(slot string) (string, string) {
	switch slot {
	case "conditions.proposition":
		return conditionsSection, propositionsField
	case "content.target":
		return contentField, nodesSection
	case "accounts.node":
		return accountsSection, nodesSection
	case "accounts.domain_ref":
		return accountsSection, identityDomainsField
	case "identity_domains.authority_account_ref":
		return identityDomainsField, accountsSection
	case "objectives.assigned_participant":
		return objectivesSection, agentsSection
	case "objectives.owner":
		return objectivesSection, entitiesField
	default:
		return "", ""
	}
}
func variationCollectionSlot(slot string) (string, string) {
	switch slot {
	case "nodes.features":
		return nodesSection, featuresSection
	case "nodes.conditions":
		return nodesSection, conditionsSection
	case "nodes.injects":
		return nodesSection, injectsSection
	case "events.assertions":
		return eventsSection, assertionsSection
	case "events.injects":
		return eventsSection, injectsSection
	case "stories.scripts":
		return storiesField, scriptsField
	case "agents.starting_accounts":
		return agentsSection, accountsSection
	case "agents.starting_assertions":
		return agentsSection, assertionsSection
	case "objectives.targets":
		return objectivesSection, "objective-subject"
	case "objectives.depends_on":
		return objectivesSection, objectivesSection
	default:
		return "", ""
	}
}
func variationTimingSlot(slot string) (string, string, string) {
	switch slot {
	case "conditions.interval":
		return conditionsSection, integerType, variationSecondsUnit
	case "scripts.start_time", "scripts.end_time":
		return scriptsField, integerType, variationSecondsUnit
	case "scripts.speed":
		return scriptsField, numberType, "multiplier"
	case "stories.speed":
		return storiesField, numberType, "multiplier"
	default:
		return "", "", ""
	}
}
