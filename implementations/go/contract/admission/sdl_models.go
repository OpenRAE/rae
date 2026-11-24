package admission

import (
	"strings"
	"unicode"
)

func probeShape(v any) error {
	command, interval, source := at(v, "command") != nil, at(v, "interval") != nil, at(v, termSource) != nil
	return require(command == interval && (command != source))
}
func contentAnchors(v any) error {
	if stringAt(v, "target") == "" {
		return invalid()
	}
	kind := stringAt(v, "type")
	if kind == termFile && stringAt(v, "path") == "" || kind == "directory" && stringAt(v, "destination") == "" {
		return invalid()
	}
	if at(v, "text_from") != nil && (at(v, "text") != nil || kind != termFile) {
		return invalid()
	}
	indexSchema := stringAt(v, "service_materialization", "interface_profile") == "service-search-index-schema"
	if indexSchema {
		return require(kind == "dataset" && at(v, termSource) == nil && len(array(at(v, "items"))) == 0)
	}
	if kind == "dataset" {
		return require(at(v, termSource) != nil || len(array(at(v, "items"))) > 0)
	}
	return nil
}
func successCriteria(v any) error {
	count := len(array(at(v, "assertions")))
	if count == 0 {
		return invalid()
	}
	threshold := at(v, "threshold")
	if stringAt(v, "mode") == "at_least" {
		n, ok := integer(threshold)
		return require(ok && n > 0 && n <= count)
	}
	return require(threshold == nil)
}
func subsetBounds(v any) error {
	members := object(at(v, "members"))
	minimum := 0
	if at(v, "minimum") != nil {
		n, ok := integer(at(v, "minimum"))
		if !ok {
			return invalid()
		}
		minimum = n
	}
	maximum := len(members)
	if at(v, "maximum") != nil {
		n, ok := integer(at(v, "maximum"))
		if !ok {
			return invalid()
		}
		maximum = n
	}
	if minimum > maximum || maximum > len(members) {
		return invalid()
	}
	refs := map[string]bool{}
	for _, member := range members {
		ref := stringAt(member, "reference")
		if refs[ref] {
			return invalid()
		}
		refs[ref] = true
	}
	return nil
}
func clockJump(v any) error {
	for _, name := range []string{"time_domain_ref", "authority_ref", termDescription} {
		if sdlBlank(stringAt(v, name)) {
			return invalid()
		}
	}
	return require((stringAt(v, "monotonicity") == "may_jump") == boolean(at(v, "supports_jump")))
}
func runtimeFilesystemModel(v any) error {
	path := stringAt(v, "path")
	if !strings.HasPrefix(path, "/") && !variableRef(path) {
		return invalid()
	}
	return require((stringAt(v, "content_digest") == "") == (stringAt(v, "digest_algorithm") == "") && sdlFilesystemMode(at(v, "mode")))
}
func sdlWhitespace(r rune) bool { return unicode.IsSpace(r) || r >= 0x1c && r <= 0x1f }
func sdlBlank(value string) bool {
	return strings.TrimFunc(value, sdlWhitespace) == ""
}

const (
	termMaxAttempts    = "max_attempts"
	termFile           = "file"
	termSwitch         = "switch"
	termObjective      = "objective"
	termScaffolded     = "scaffolded"
	termBranches       = "branches"
	termElse           = "else"
	termCompensateWith = "compensate_with"
	termDefault        = "default"
	termVersion        = "version"
)

func augmentationScopeModel(v any) error {
	identities := []string{}
	for _, rule := range array(at(v, "scopes")) {
		identities = append(identities, join(append(stringsOf(at(rule, termNamespace)), stringAt(rule, "scope"))...))
	}
	return require(unique(identities))
}
func behaviorSpecificationModel(v any) error {
	if err := behaviorReferences(v); err != nil {
		return err
	}
	policy := text(defaultMember(v, "extension_policy", "governed-extension"))
	if policy != "governed-extension" && policy != "closed" || policy == "closed" && len(object(at(v, "extensions"))) > 0 {
		return invalid()
	}
	if len(array(at(v, "participant_refs"))) == 0 && len(array(at(v, "participant_role_refs"))) == 0 {
		return invalid()
	}
	for _, field := range []string{"action_contract_refs", "observation_boundary_refs", "outcome_interpretation_rule_refs", fieldAuthorityScopeRefs, "backend_feature_support_refs", "evidence_contract_refs", "tool_affordances", "participant_inject_deliveries", "control_context"} {
		if len(array(at(v, field))) > 0 || len(object(at(v, field))) > 0 {
			return nil
		}
	}
	for _, field := range []string{"behavior_mode", "autonomous_execution", "mixed_control", "realization_profile_ref"} {
		if at(v, field) != nil {
			return nil
		}
	}
	return invalid()
}

const (
	termDescription      = "description"
	termSource           = "source"
	termEnvironment      = "environment"
	termForwardingAgents = "forwarding_agents"
)

const (
	termRedacted = "redacted"
	termSourceID = "source_id"
	termResult   = "result"
)

const (
	termPID       = "pid"
	termParentPID = "parent_pid"
	termGroup     = "group"
	termUnlimited = "unlimited"
)

const termUser = "user"

const (
	termObservationID    = "observation_id"
	termRoles            = "roles"
	termWorkingDirectory = "working_directory"
	termMySQL            = "mysql"
)

const (
	termNodes     = "nodes"
	termMappingID = "mapping_id"
	termSettings  = "settings"
)

const (
	termComponentID = "component_id"
	termBindingID   = "binding_id"
	termDomains     = "domains"
	termSettingID   = "setting_id"
)

const (
	termDisclosure = "disclosure"
	termDeceptive  = "deceptive"
)

const (
	termAuthorityBasisRefs = "authority_basis_refs"
	termScopeRefs          = "scope_refs"
	termContinuous         = "continuous"
	termDiscovered         = "discovered"
)

const (
	termInferred = "inferred"
)

const termEpisode = "episode"

const (
	termMaterializationSpecification = "materialization-specification"
	termWindowRef                    = "window_ref"
	termDurationRef                  = "duration_ref"
	termDwell                        = "dwell"
	termStart                        = "start"
	termEnd                          = "end"
	termEffective                    = "effective"
)
