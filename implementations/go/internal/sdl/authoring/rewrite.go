package authoring

import (
	"encoding/json"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// These paths identify owned references. Wildcards visit declared collection
// elements; they never discover reference-looking strings in opaque payloads.
const referencePaths = `
nodes/*/features/@keys features
nodes/*/conditions/@keys conditions
nodes/*/injects/@keys injects
nodes/*/roles/*/entities entities
nodes/*/runtime/container/namespaces/network/target_node_ref =nodes
nodes/*/runtime/environment/*/value_from/generated_artifact =generated_artifacts
nodes/*/runtime/environment_files/*/value_from/generated_artifact =generated_artifacts
nodes/*/runtime/mail_services/*/mailboxes/*/account_ref =accounts
nodes/*/runtime/security_monitoring_managers/*/detection_definitions/*/source_artifact_ref named
nodes/*/runtime/network_detection_engines/*/rule_sources/*/generated_by named
infrastructure/*/acls/*/from_net infrastructure
infrastructure/*/acls/*/to_net infrastructure
infrastructure/*/dependencies named
infrastructure/*/links named
infrastructure/*/properties/*/@keys named
features/*/dependencies features
entities/**/events events
conditions/*/proposition propositions
propositions/*/subjects named
propositions/*/evidence_requirements evidence_requirements
propositions/*/predicate/expected_from/generated_artifact =generated_artifacts
assertions/*/proposition propositions
injects/*/from_entity entities
injects/*/to_entities entities
events/*/assertions assertions
events/*/injects injects
scripts/*/events/@keys events
stories/*/scripts scripts
observation_boundaries/*/observable_refs named
observation_boundaries/*/hidden_refs named
observation_boundaries/*/evidence_refs named
observation_boundaries/*/view_rules/*/evidence_refs named
observation_boundaries/*/view_rules/*/information_ref named
observation_boundaries/*/view_transitions/*/evidence_refs named
observation_boundaries/*/view_transitions/*/information_ref named
content/*/target =nodes
content/*/text_from/generated_artifact =generated_artifacts
content/*/service_materialization/target_service_ref !node-service
content/*/service_materialization/shared_service_relationship_ref =relationships
content/*/service_materialization/ordering_content_refs =content
content/*/service_materialization/readback_assertion_refs =assertions
content/*/service_materialization/evidence_requirement_refs =evidence_requirements
content/*/service_materialization/observation_boundary_refs =observation_boundaries
generated_artifacts/*/consumers/*/node =nodes
persistent_volumes/*/consumers/*/node =nodes
generated_artifacts/*/ordering_dependencies !stateful
generated_artifacts/*/refresh_dependencies !stateful
persistent_volumes/*/ordering_dependencies !stateful
persistent_volumes/*/refresh_dependencies !stateful
accounts/*/node nodes
accounts/*/domain_ref identity_domains
identity_domains/*/authority_account_ref accounts
identity_forests/*/root_domain_ref identity_domains
identity_forests/*/domain_refs identity_domains
identity_facades/*/service_ref named
deployment_cells/*/tenant_ref deployment_tenants
deployment_cells/*/node_refs nodes
relationships/*/source named
relationships/*/target named
relationships/*/domain_join/controller_refs nodes
relationships/*/shared_service/mutable_state_refs persistent_volumes
relationships/*/forwarding_edge/forwarder_ref forwarding_agents
relationships/*/participant/source_action_refs =action_contracts
relationships/*/participant/target_action_refs =action_contracts
relationships/*/participant/objective_refs =objectives
relationships/*/participant/behavior_specification_refs =behavior_specifications
relationships/*/participant/authority_basis_refs named
relationships/*/participant/scope_refs named
relationships/*/participant/observation_boundary_refs =observation_boundaries
relationships/*/participant/control_specification_ref =behavior_specifications
agents/*/affiliations entities
agents/*/starting_accounts accounts
agents/*/actions action_contracts
agents/*/observation_boundaries observation_boundaries
agents/*/allowed_subnets infrastructure
agents/*/starting_assertions assertions
agents/*/authority_anchors named
agents/*/operating_scope named
agents/*/control_context/*/declaration_ref !control-asset
agents/*/interactive_access/*/target_ref =nodes
agents/*/interactive_access/*/account_ref =accounts
agents/*/initial_knowledge/hosts nodes
agents/*/initial_knowledge/subnets infrastructure
agents/*/initial_knowledge/accounts accounts
behavior_specifications/*/participant_refs agents
behavior_specifications/*/action_contract_refs action_contracts
behavior_specifications/*/observation_boundary_refs observation_boundaries
behavior_specifications/*/outcome_interpretation_rule_refs outcome_interpretation_rules
behavior_specifications/*/authority_scope_refs named
behavior_specifications/*/control_context/*/declaration_ref !control-asset
behavior_specifications/*/tool_affordances/*/tool_ref !tool
behavior_specifications/*/tool_affordances/*/action_contract_refs action_contracts
behavior_specifications/*/tool_affordances/*/observation_boundary_refs observation_boundaries
behavior_specifications/*/tool_affordances/*/participant_refs agents
behavior_specifications/*/mixed_control/participant_ref agents
behavior_specifications/*/mixed_control/controller_states/*/controller_ref !controller
behavior_specifications/*/mixed_control/controller_states/*/authority_basis_refs named
behavior_specifications/*/mixed_control/controller_states/*/scope_refs named
behavior_specifications/*/mixed_control/controller_states/*/evidence_refs named
behavior_specifications/*/mixed_control/transitions/*/evidence_refs named
behavior_specifications/*/mixed_control/transitions/*/completion_evidence_refs named
behavior_specifications/*/mixed_control/permitted_transitions/*/evidence_refs named
behavior_specifications/*/mixed_control/permitted_transitions/*/completion_evidence_refs named
behavior_specifications/*/participant_inject_deliveries/*/participant_ref agents
behavior_specifications/*/participant_inject_deliveries/*/inject_ref injects
behavior_specifications/*/participant_inject_deliveries/*/occurrence/event_ref events
behavior_specifications/*/participant_inject_deliveries/*/occurrence/script_ref scripts
behavior_specifications/*/participant_inject_deliveries/*/occurrence/story_ref stories
behavior_specifications/*/participant_inject_deliveries/*/source_item_ref named
behavior_specifications/*/participant_inject_deliveries/*/result_item_ref named
behavior_specifications/*/participant_inject_deliveries/*/observation_boundary_ref observation_boundaries
behavior_specifications/*/participant_inject_deliveries/*/temporal_constraint_refs temporal_constraints
behavior_specifications/*/participant_inject_deliveries/*/evidence_requirement_refs evidence_requirements
behavior_specifications/*/participant_inject_deliveries/*/controller_ref !controller
behavior_specifications/*/participant_inject_deliveries/*/control_authority_scope_refs named
behavior_specifications/*/participant_inject_deliveries/*/control_evidence_refs named
behavior_specifications/*/participant_inject_deliveries/*/control/controller_ref !controller
behavior_specifications/*/participant_inject_deliveries/*/control/authority_scope_refs named
behavior_specifications/*/participant_inject_deliveries/*/control/evidence_refs named
behavior_specifications/*/autonomous_execution/clock_ref =clocks
behavior_specifications/*/autonomous_execution/progression_policy_ref =time_progression_policies
behavior_specifications/*/autonomous_execution/observation_boundary_ref =observation_boundaries
behavior_specifications/*/autonomous_execution/action_order =action_contracts
behavior_specifications/*/autonomous_execution/temporal_constraint_refs =temporal_constraints
behavior_specifications/*/autonomous_execution/work_window_refs =temporal_constraints
behavior_specifications/*/autonomous_execution/pause_window_refs =temporal_constraints
behavior_specifications/*/autonomous_execution/action_candidates/*/action_ref =action_contracts
behavior_specifications/*/autonomous_execution/evaluation_authority/objective_refs =objectives
behavior_specifications/*/autonomous_execution/resource_budget/owners/* !budget-owner
action_contracts/*/preconditions/*/support_refs named
action_contracts/*/preconditions/*/evidence_refs named
action_contracts/*/effects/*/target_refs named
action_contracts/*/effects/*/evidence_refs named
action_contracts/*/interactions/*/target named
action_contracts/*/interactions/*/related_actions action_contracts
action_contracts/*/interactions/*/shared_state_refs named
action_contracts/*/temporal_contracts/*/shared_time_binding/clock_ref =clocks
action_contracts/*/temporal_contracts/*/shared_time_binding/constraint_ref =temporal_constraints
action_contracts/*/temporal_contracts/*/shared_time_binding/observation_boundary_ref =observation_boundaries
outcome_interpretation_rules/*/source_bindings/* !outcome-source
outcome_interpretation_rules/*/target_bindings/* !outcome-target
outcome_interpretation_rules/*/source_bindings/*/evidence_refs named
outcome_interpretation_rules/*/source_bindings/*/provenance_refs named
outcome_interpretation_rules/*/target_bindings/*/evidence_refs named
outcome_interpretation_rules/*/target_bindings/*/provenance_refs named
outcome_interpretation_rules/*/evidence_refs named
evidence_requirements/*/source_refs named
evidence_requirements/*/scope_refs named
evidence_requirements/*/channel_refs named
evidence_requirements/*/trigger_ref named
evidence_requirements/*/boundary_ref named
clocks/*/time_domain_ref time_domains
time_domain_mappings/*/source_domain_ref time_domains
time_domain_mappings/*/target_domain_ref time_domains
time_progression_policies/*/clock_ref clocks
temporal_constraints/*/clock_ref clocks
temporal_constraints/*/subject_refs named
objectives/*/assigned_participant agents
objectives/*/owner entities
objectives/*/actions action_contracts
objectives/*/targets named
objectives/*/depends_on objectives
objectives/*/success/assertions assertions
objectives/*/window/stories stories
objectives/*/window/scripts scripts
objectives/*/window/events events
objectives/*/window/workflows workflows
objectives/*/window/steps !workflow-step
workflows/*/steps/*/objective objectives
workflows/*/steps/*/procedure_ref action_contracts
workflows/*/steps/*/scaffold_refs observation_boundaries
workflows/*/steps/*/allowed_action_families action_contracts
workflows/*/steps/*/tool_affordance_refs named
workflows/*/steps/*/workflow workflows
workflows/*/steps/*/compensate_with workflows
workflows/*/steps/*/when/assertions assertions
workflows/*/steps/*/when/objectives objectives
variation_points/* !variation
accounts/*/materialization_profile !profile
generated_artifacts/*/generator !profile
content/*/service_materialization !profile
identity_domains/*/profile !profile
identity_facades/*/protocol !profile
relationships/*/forest_trust/trust_type !profile
relationships/*/identity_federation/protocol !profile
relationships/*/identity_federation/mapping_intent !profile
agents/*/interactive_access/*/channel !profile
`

func rewriteOwnedReferences(value map[string]any, symbols importSymbols) error {
	return rewriteOwnedReferencesWithBudget(value, symbols, &copyBudget{remaining: source.DefaultLimits().MaxComposedBytes})
}
func rewriteOwnedReferencesWithBudget(value map[string]any, symbols importSymbols, copies *copyBudget) error {
	if symbols[termNamed] == nil {
		completeSymbols(value, symbols)
	}
	for line := range strings.SplitSeq(referencePaths, "\n") {
		fields := strings.Fields(line)
		if len(fields) == 0 {
			continue
		}
		if _, err := rewritePath(value, strings.Split(fields[0], "/"), symbols, fields[1]); err != nil {
			return err
		}
	}
	if err := rewriteCloudReferences(value, symbols); err != nil {
		return err
	}
	return rewriteVariables(value, symbols, copies)
}
func rewriteVariables(value map[string]any, symbols importSymbols, copies *copyBudget) error {
	if len(symbols[variablesSection]) == 0 {
		return nil
	}
	rename := substitution{values: map[string]any{}, keepUnknown: true, copies: copies, inline: map[string]string{}}
	for old, next := range symbols[variablesSection] {
		rename.values[old] = "${" + next + "}"
	}
	for key, raw := range value {
		if key == controlAssetsSection {
			continue
		}
		next, err := rename.walk(raw)
		if err != nil {
			return err
		}
		value[key] = next
	}
	return nil
}
func completeSymbols(value map[string]any, symbols importSymbols) {
	named := map[string]string{}
	for _, section := range declarationSections() {
		for old, next := range symbols[section] {
			named[old] = next
			named[section+"."+old] = section + "." + next
		}
	}
	symbols[termNamed] = named
	addNestedSymbols(value, symbols)
	for old, next := range symbols[forwardingSection] {
		named[forwardingSection+"."+old] = forwardingSection + "." + next
	}
}
func addNestedSymbols(value map[string]any, symbols importSymbols) {
	for address, declaration := range indexDeclarations(value).declarations {
		if len(declaration.tokens) < 3 {
			continue
		}
		section, owner := declaration.tokens[0], declaration.tokens[1]
		if section != nodesSection && section != contentField && section != behaviorSection {
			continue
		}
		if next, known := symbols[section][owner]; known && next != owner {
			symbols[termNamed][address] = section + "." + next + strings.TrimPrefix(address, section+"."+owner)
		}
	}
}
func rewritePath(value any, tokens []string, symbols importSymbols, domain string) (any, error) {
	if len(tokens) == 0 {
		return rewriteReferenceValue(value, symbols, domain)
	}
	head, tail := tokens[0], tokens[1:]
	switch head {
	case "**":
		return rewriteDescendants(value, tail, tokens, symbols, domain)
	case "@keys":
		return value, rewriteMappingKeys(object(value), symbols, domain)
	default:
		return rewriteChildren(value, head, tail, symbols, domain)
	}
}
func rewriteDescendants(value any, tail, recursive []string, symbols importSymbols, domain string) (any, error) {
	if _, err := rewritePath(value, tail, symbols, domain); err != nil {
		return nil, err
	}
	for _, child := range object(value) {
		if _, err := rewritePath(child, recursive, symbols, domain); err != nil {
			return nil, err
		}
	}
	return value, nil
}
func rewriteMappingKeys(mapping map[string]any, symbols importSymbols, domain string) error {
	replacement := map[string]any{}
	for key, item := range mapping {
		next, err := rewriteReference(key, symbols, domain)
		if err != nil {
			return err
		}
		if _, exists := replacement[next]; exists {
			return importError("collision")
		}
		replacement[next] = item
	}
	clear(mapping)
	maps.Copy(mapping, replacement)
	return nil
}
func rewriteChildren(value any, head string, tail []string, symbols importSymbols, domain string) (any, error) {
	if mapping := object(value); mapping != nil {
		for key, item := range mapping {
			if head != "*" && head != key {
				continue
			}
			next, err := rewritePath(item, tail, symbols, domain)
			if err != nil {
				return nil, err
			}
			mapping[key] = next
		}
		return value, nil
	}
	return rewriteChildItems(value, head, tail, symbols, domain)
}
func rewriteChildItems(value any, head string, tail []string, symbols importSymbols, domain string) (any, error) {
	if items, ok := value.([]any); ok && head == "*" {
		for index, item := range items {
			next, err := rewritePath(item, tail, symbols, domain)
			if err != nil {
				return nil, err
			}
			items[index] = next
		}
	}
	return value, nil
}
func rewriteReferenceValue(value any, symbols importSymbols, domain string) (any, error) {
	if object(value) != nil && strings.HasPrefix(domain, "!") {
		return rewriteReferenceObject(object(value), symbols, domain)
	}
	if reference, ok := value.(string); ok {
		return rewriteReference(reference, symbols, domain)
	}
	if items, ok := value.([]any); ok {
		for index, item := range items {
			next, err := rewriteReferenceValue(item, symbols, domain)
			if err != nil {
				return nil, err
			}
			items[index] = next
		}
	}
	return value, nil
}
func rewriteReference(reference string, symbols importSymbols, domain string) (string, error) {
	if reference == "" || variable(reference) {
		return reference, nil
	}
	switch domain {
	case "!control-asset":
		if next, known := symbols[controlAssetsSection][reference]; known {
			return next, nil
		}
		domain = termNamed
	case "!tool":
		if next, known := symbols[contentField][reference]; known {
			return next, nil
		}
		domain = termNamed
	case "!controller":
		if reference == "self" {
			return reference, nil
		}
		domain = agentsSection
	case "!workflow-step":
		return rewriteWorkflowStep(reference, symbols), nil
	case "!node-service":
		return rewriteNodeService(reference, symbols)
	case "!stateful":
		return rewriteStateful(reference, symbols)
	}
	return rewriteSectionReference(reference, symbols, domain), nil
}
func rewriteSectionReference(reference string, symbols importSymbols, domain string) string {
	section, qualified := strings.CutPrefix(domain, "=")
	if qualified {
		if local, explicit := strings.CutPrefix(reference, section+"."); explicit {
			if next, known := symbols[section][local]; known {
				return section + "." + next
			}
			return reference
		}
		domain = section
	}
	if next, known := symbols[domain][reference]; known {
		return next
	}
	return reference
}
func rewriteWorkflowStep(reference string, symbols importSymbols) string {
	index := strings.LastIndex(reference, ".")
	if index > 0 {
		if next, known := symbols[workflowsSection][reference[:index]]; known {
			return next + reference[index:]
		}
	}
	return reference
}
func rewriteNodeService(reference string, symbols importSymbols) (string, error) {
	for old, next := range symbols[nodesSection] {
		if strings.HasPrefix(reference, "nodes."+old+".services.") {
			return "nodes." + next + strings.TrimPrefix(reference, "nodes."+old), nil
		}
	}
	return rewriteSectionReference(reference, symbols, "=nodes"), nil
}
func rewriteStateful(reference string, symbols importSymbols) (string, error) {
	matches := []string{}
	for _, section := range []string{generatedArtifactsField, persistentVolumesField} {
		if strings.HasPrefix(reference, section+".") {
			return rewriteSectionReference(reference, symbols, "="+section), nil
		}
		if _, known := symbols[section][reference]; known {
			matches = append(matches, section)
		}
	}
	if len(matches) > 1 {
		return "", invalid()
	}
	if len(matches) == 0 {
		return reference, nil
	}
	return rewriteSectionReference(reference, symbols, "="+matches[0]), nil
}
func rewriteDeclarationKeys(value map[string]any, symbols importSymbols) error {
	for _, section := range declarationSections() {
		if _, err := rewritePath(value, []string{section, "@keys"}, symbols, section); err != nil {
			return err
		}
	}
	_, err := rewritePath(value, []string{forwardingSection, "*", termForwardingAgentID}, symbols, forwardingSection)
	return err
}
func rewriteReferenceObject(value map[string]any, symbols importSymbols, domain string) (any, error) {
	switch domain {
	case "!variation":
		return value, rewriteVariationReferences(value, symbols)
	case "!profile":
		return value, rewriteProfileOwner(value, symbols)
	case "!budget-owner":
		kind := text(value[kindField])
		target := ""
		switch kind {
		case "participant":
			target = "=agents"
		case termDeploymentTenant:
			target = "=deployment_tenants"
		case "shared_service":
			target = "!node-service"
		}
		if target != "" {
			_, err := rewritePath(value, []string{"ref"}, symbols, target)
			return value, err
		}
	case "!outcome-source", "!outcome-target":
		layer := "source_layer"
		if domain == "!outcome-target" {
			layer = "target_layer"
		}
		target := ""
		switch text(value[layer]) {
		case "participant_action_outcome":
			target = actionsSection
		case "objective_result":
			target = objectivesSection
		case "workflow_result":
			target = workflowsSection
		}
		if target != "" {
			_, err := rewritePath(value, []string{"ref"}, symbols, target)
			return value, err
		}
	}
	return value, nil
}
func rewriteProfileOwner(value map[string]any, symbols importSymbols) error {
	owner := object(value[termOwner])
	if owner == nil {
		return nil
	}
	before := text(owner["canonical_address"])
	after := rewriteProfileAddress(before, symbols)
	owner["canonical_address"] = after
	if before != after {
		raw, err := json.Marshal(map[string]any{termOwner: after, "binding_id": value["binding_id"]})
		if err != nil {
			return invalid()
		}
		canonical, err := canonjson.JCS(raw)
		if err != nil {
			return err
		}
		value["binding_id"] = "composed-" + strings.TrimPrefix(digest.SHA256(canonical), sha256Prefix)
	}
	if owner["context"] == "account-materialization" {
		if _, err := rewritePath(value, []string{"value", "mailbox_ref"}, symbols, termNamed); err != nil {
			return err
		}
	}
	for _, child := range array(value["children"]) {
		if err := rewriteProfileOwner(object(child), symbols); err != nil {
			return err
		}
	}
	return nil
}
func rewriteProfileAddress(address string, symbols importSymbols) string {
	if strings.HasPrefix(address, "#/resources/") {
		return rewriteCompiledProfileAddress(address, symbols)
	}
	if strings.HasPrefix(address, "#/") {
		return "#" + symbols.pointer(strings.TrimPrefix(address, "#"))
	}
	if strings.HasPrefix(address, "/") {
		return symbols.pointer(address)
	}
	return address
}
func rewriteCompiledProfileAddress(address string, symbols importSymbols) string {
	for kind, section := range map[string]string{termNode: nodesSection, "account": accountsSection, "content": contentField, "generated-artifact": generatedArtifactsField, "persistent-volume": persistentVolumesField} {
		prefix := "#/resources/provision." + kind + "."
		if local, known := strings.CutPrefix(address, prefix); known {
			if next, found := symbols[section][local]; found {
				return prefix + next
			}
			return address
		}
	}
	return rewriteDomainControllerAddress(address, symbols)
}
func rewriteDomainControllerAddress(address string, symbols importSymbols) string {
	prefix := "#/resources/provision.domain-controller."
	if local, known := strings.CutPrefix(address, prefix); known {
		for domain, nextDomain := range symbols[identityDomainsField] {
			if node, found := strings.CutPrefix(local, domain+"."); found {
				if nextNode, ok := symbols[nodesSection][node]; ok {
					return prefix + nextDomain + "." + nextNode
				}
			}
		}
	}
	return address
}
func rewriteVariationReferences(point map[string]any, symbols importSymbols) error {
	target := object(point["target"])
	slot := text(target["slot"])
	owner, referent := variationReferenceSlot(slot)
	if owner == "" {
		owner, referent = variationCollectionSlot(slot)
	}
	if owner == "" {
		owner, _, _ = variationTimingSlot(slot)
	}
	if owner == "" {
		owner, _, _ = strings.Cut(slot, ".")
	}
	if _, err := rewritePath(target, []string{termVariable}, symbols, variablesSection); err != nil {
		return err
	}
	ownerDomain := "=" + owner
	if strings.HasPrefix(slot, "nodes.runtime.") {
		ownerDomain = termNamed
	}
	if _, err := rewritePath(target, []string{termOwner}, symbols, ownerDomain); err != nil {
		return err
	}
	targetDomain := "=" + referent
	if symbols[referent] == nil {
		targetDomain = termNamed
	}
	if point[kindField] == termGovernedReference {
		if _, err := rewritePath(point, []string{termDomain, "allowed_refs"}, symbols, targetDomain); err != nil {
			return err
		}
	}
	return rewriteVariationMembers(point, symbols, targetDomain)
}
func rewriteVariationMembers(point map[string]any, symbols importSymbols, targetDomain string) error {
	for _, field := range []string{termMembers, termAlternatives} {
		for _, raw := range object(point[field]) {
			member := object(raw)
			for _, rule := range []struct {
				path   []string
				domain string
			}{{[]string{termReference}, targetDomain}, {[]string{"references"}, termNamed}, {[]string{"inventory", "*"}, termNamed}, {[]string{termConsumers, "*", termNode}, "=nodes"}, {[]string{"requires", "*", "point"}, variationPointsField}, {[]string{"excludes", "*", "point"}, variationPointsField}} {
				if _, err := rewritePath(member, rule.path, symbols, rule.domain); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
