package planning

import (
	"encoding/json"
	"math/big"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

type orchestratorCapabilities struct {
	SupportedSections                []string `json:"supported_sections"`
	SupportsWorkflows                bool     `json:"supports_workflows"`
	SupportedWorkflowFeatures        []string `json:"supported_workflow_features"`
	SupportsAssertionRefs            bool     `json:"supports_assertion_refs"`
	SupportedWorkflowStatePredicates []string `json:"supported_workflow_state_predicates"`
	SupportsInjectBindings           bool     `json:"supports_inject_bindings"`
}
type evaluatorCapabilities struct {
	SupportedSections                  []string `json:"supported_sections"`
	SupportsObjectives                 *bool    `json:"supports_objectives"`
	SupportedPredicateFamilies         []string `json:"supported_predicate_families"`
	SupportsDeferredExpectedComparison bool     `json:"supports_deferred_expected_comparison"`
	SupportedQuantifiers               []string `json:"supported_quantifiers"`
	SupportedEvidenceChannels          []string `json:"supported_evidence_channels"`
	SupportedTimeDomains               []string `json:"supported_time_domains"`
}

// Optional manifest components are JSON leaves in the published transport.
// Decode them once at this admitted boundary; resource semantics stay typed.
func manifestDiagnostics(model processor.CompiledScenario, manifest binding.BackendManifestV2) ([]diagnostic.Diagnostic, error) {
	caps := fieldValue(manifest.Capabilities)
	kinds := map[string][]processor.Resource{}
	for _, resource := range model.Resources {
		kinds[resource.Kind] = append(kinds[resource.Kind], resource)
	}
	deployments := append(slices.Clone(kinds[termNetwork]), kinds[termNode]...)
	result := networkCapabilityDiagnostics(kinds, deployments, manifest)
	domains, err := newCapabilityDomains(model)
	if err != nil {
		return nil, err
	}
	for _, resource := range kinds[termNode] {
		findings, nodeErr := nodeCapabilityDiagnostics(resource, domains, manifest)
		if nodeErr != nil {
			return nil, nodeErr
		}
		result = append(result, findings...)
	}
	maxima, err := maximumNodeDiagnostics(deployments, domains, manifest)
	if err != nil {
		return nil, err
	}
	result = append(result, maxima...)
	result = append(result, contentCapabilityDiagnostics(kinds, manifest)...)
	result = append(result, accountCapabilityDiagnostics(kinds, manifest)...)
	result = append(result, artifactAndVolumeDiagnostics(kinds, manifest)...)
	orchestration, err := orchestrationDiagnostics(kinds, fieldValue(caps.Orchestrator))
	if err != nil {
		return nil, err
	}
	result = append(result, orchestration...)
	evaluation, err := evaluationDiagnostics(kinds, fieldValue(caps.Evaluator))
	if err != nil {
		return nil, err
	}
	return append(result, evaluation...), nil
}

func networkCapabilityDiagnostics(kinds map[string][]processor.Resource, deployments []processor.Resource, manifest binding.BackendManifestV2) []diagnostic.Diagnostic {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	for _, resource := range deployments {
		if resource.HasACLs && !fieldValue(p.SupportsAcls) {
			add("provisioner.acls-unsupported", resource.Address, "Provisioner does not support ACL declarations.")
		}
	}
	for _, resource := range kinds[termNetwork] {
		if !slices.Contains(fieldValue(p.SupportedNodeTypes), "switch") {
			add("provisioner.unsupported-node-type", resource.Address, "Provisioner does not support switch/network nodes.")
		}
	}
	return result
}

func nodeCapabilityDiagnostics(resource processor.Resource, domains *capabilityDomainIndex, manifest binding.BackendManifestV2) ([]diagnostic.Diagnostic, error) {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	node := resource.Node
	if node == nil {
		return nil, invalidPlan()
	}
	if node.Kind != "" && !slices.Contains(fieldValue(p.SupportedNodeTypes), node.Kind) {
		add("provisioner.unsupported-node-type", resource.Address, "Provisioner does not support node kind '"+node.Kind+"'.")
	}
	result = append(result, domains.scalarSupport(resource, termOsFamily, "nodes.os", node.OSFamily, fieldValue(p.SupportedOsFamilies), false)...)
	if domains.hasOSRequirements[resource.Address] {
		result = append(result, operatingSystemDiagnostics(resource, domains, manifest)...)
	}
	result = append(result, domains.scalarSupport(resource, "node-architecture", "nodes.architecture", node.Architecture, fieldValue(p.SupportedNodeArchitectures), true)...)
	return result, nil
}

func operatingSystemDiagnostics(resource processor.Resource, domains *capabilityDomainIndex, manifest binding.BackendManifestV2) []diagnostic.Diagnostic {
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	node := resource.Node
	family, fd := domains.domain(resource, termOsFamily, "nodes.os", node.OSFamily)
	distribution, dd := domains.domain(resource, termOsDistribution, "nodes.os_distribution", node.OSDistribution)
	version, vd := domains.domain(resource, termOsVersion, "nodes.os_version", node.OSVersion)
	var failure *diagnostic.Diagnostic
	for _, d := range []*diagnostic.Diagnostic{fd, dd, vd} {
		if d != nil {
			failure = d
			break
		}
	}
	if failure != nil {
		result = append(result, *failure)
	} else {
		found := jointOperatingSystemOffered(manifest, family, distribution, version)
		if !found {
			add("provisioner.unsupported-operating-system", resource.Address, "Provisioner has no coupled operating-system compatibility row intersecting the authored exact, constrained, and open OS domains.")
		}
	}
	return result
}

func jointOperatingSystemOffered(manifest binding.BackendManifestV2, family, distribution, version []string) bool {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	for _, row := range fieldValue(p.OperatingSystems) {
		if family != nil && !slices.Contains(family, fieldValue(row.Family)) || distribution != nil && !slices.Contains(distribution, fieldValue(row.Distribution)) {
			continue
		}
		for _, choice := range fieldValue(row.Versions) {
			if version == nil || slices.Contains(version, choice) {
				return true
			}
		}
	}
	return false
}

func maximumNodeDiagnostics(deployments []processor.Resource, domains *capabilityDomainIndex, manifest binding.BackendManifestV2) ([]diagnostic.Diagnostic, error) {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	if maximum := fieldValue(p.MaxTotalNodes); len(maximum) > 0 && string(maximum) != termNull {
		ceiling, ok := capabilityInteger(json.Number(maximum))
		if !ok {
			return nil, invalidPlan()
		}
		total := new(big.Int)
		for _, resource := range deployments {
			count, d := domains.count(resource)
			if d != nil {
				result = append(result, *d)
			}
			if count != nil {
				total.Add(total, count)
			}
		}
		if total.Cmp(ceiling) > 0 {
			add("provisioner.max-total-nodes-exceeded", "provision", "Scenario requires "+total.String()+" deployable nodes/networks, but provisioner maximum is "+ceiling.String()+".")
		}
	}
	return result, nil
}

func capabilityInteger(value json.Number) (*big.Int, bool) {
	// The manifest admission owner bounds numeric work before these checks.
	// Integral JSON values need not use the plain integer spelling.
	number, ok := new(big.Rat).SetString(string(value))
	if !ok || !number.IsInt() {
		return nil, false
	}
	return number.Num(), true
}

func contentCapabilityDiagnostics(kinds map[string][]processor.Resource, manifest binding.BackendManifestV2) []diagnostic.Diagnostic {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	for _, resource := range kinds[termContentPlacement] {
		if resource.ContentType != "" && !slices.Contains(fieldValue(p.SupportedContentTypes), resource.ContentType) {
			add("provisioner.unsupported-content-type", resource.Address, "Provisioner does not support content type '"+resource.ContentType+"'.")
		}
	}
	return result
}

func accountCapabilityDiagnostics(kinds map[string][]processor.Resource, manifest binding.BackendManifestV2) []diagnostic.Diagnostic {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	if len(kinds["account-placement"]) > 0 && !fieldValue(p.SupportsAccounts) {
		add("provisioner.accounts-unsupported", "provision.accounts", "Provisioner does not support accounts.")
	} else {
		for _, resource := range kinds["account-placement"] {
			for _, feature := range resource.AccountFeatures {
				if !slices.Contains(fieldValue(p.SupportedAccountFeatures), feature) {
					add("provisioner.unsupported-account-feature", resource.Address, "Provisioner does not support account feature '"+feature+"'.")
				}
			}
		}
	}
	return result
}

func artifactAndVolumeDiagnostics(kinds map[string][]processor.Resource, manifest binding.BackendManifestV2) []diagnostic.Diagnostic {
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termProvisioning, address, message))
	}
	if len(kinds[termGeneratedArtifact]) > 0 && !fieldValue(p.SupportsGeneratedArtifacts) {
		add("provisioner.generated-artifacts-unsupported", "provision.generated-artifacts", "Provisioner does not support generated artifacts.")
	} else {
		result = append(result, artifactCapabilityDiagnostics(kinds[termGeneratedArtifact], fieldValue(p.SupportedGeneratedArtifactKinds), enumStrings(fieldValue(p.SupportedGeneratedArtifactDeliveryModes)), enumStrings(fieldValue(p.SupportedRegenerationScopes)))...)
	}
	if len(kinds["persistent-volume"]) > 0 && !fieldValue(p.SupportsPersistentVolumes) {
		add("provisioner.persistent-volumes-unsupported", "provision.persistent-volumes", "Provisioner does not support persistent volumes.")
	}
	return result
}

func sectionUsage(kinds map[string][]processor.Resource, definitions [][2]string) ([]string, bool) {
	used := []string{}
	for _, item := range definitions {
		if len(kinds[item[0]]) > 0 && !slices.Contains(used, item[1]) {
			used = append(used, item[1])
		}
	}
	return used, len(used) > 0
}
func orchestrationDiagnostics(kinds map[string][]processor.Resource, raw json.RawMessage) ([]diagnostic.Diagnostic, error) {
	sections, used := sectionUsage(kinds, [][2]string{{"inject", "injects"}, {"inject-binding", "injects"}, {"event", "events"}, {"script", "scripts"}, {"story", "stories"}, {"workflow", "workflows"}})
	result := []diagnostic.Diagnostic{}
	if !used {
		return result, nil
	}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termOrchestration, address, message))
	}
	if len(raw) == 0 || string(raw) == termNull {
		add("orchestrator.missing", termOrchestration, "Scenario requires orchestration support, but no orchestrator is configured.")
		return result, nil
	}
	var caps orchestratorCapabilities
	if json.Unmarshal(raw, &caps) != nil {
		return nil, invalidPlan()
	}
	for _, section := range sections {
		if !slices.Contains(caps.SupportedSections, section) {
			add("orchestrator.unsupported-section", "orchestration."+section, "Orchestrator does not support '"+section+"'.")
		}
	}
	if len(kinds["workflow"]) > 0 && !caps.SupportsWorkflows {
		add("orchestrator.workflows-unsupported", "orchestration.workflows", "Orchestrator does not support workflows.")
	}
	result = append(result, workflowCapabilityDiagnostics(kinds, caps)...)
	if len(kinds["inject-binding"]) > 0 && !caps.SupportsInjectBindings {
		add("orchestrator.inject-bindings-unsupported", "orchestration.injects", "Orchestrator does not support node-bound injects.")
	}
	return result, nil
}
func evaluationDiagnostics(kinds map[string][]processor.Resource, raw json.RawMessage) ([]diagnostic.Diagnostic, error) {
	sections, used := sectionUsage(kinds, [][2]string{{"condition-binding", "conditions"}, {"proposition", "propositions"}, {"assertion", "assertions"}, {"objective", "objectives"}})
	result := []diagnostic.Diagnostic{}
	if !used {
		return result, nil
	}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termEvaluation, address, message))
	}
	if len(raw) == 0 || string(raw) == termNull {
		add("evaluator.missing", termEvaluation, "Scenario requires evaluation support, but no evaluator is configured.")
		return result, nil
	}
	var caps evaluatorCapabilities
	if json.Unmarshal(raw, &caps) != nil {
		return nil, invalidPlan()
	}
	for _, section := range sections {
		if !slices.Contains(caps.SupportedSections, section) {
			add("evaluator.unsupported-section", "evaluation."+section, "Evaluator does not support '"+section+"'.")
		}
	}
	if len(kinds["objective"]) > 0 && caps.SupportsObjectives != nil && !*caps.SupportsObjectives {
		add("evaluator.objectives-unsupported", "evaluation.objectives", "Evaluator does not support objectives.")
	}
	if !slices.Contains(caps.SupportedSections, "propositions") {
		return result, nil
	}
	for _, resource := range kinds["proposition"] {
		findings, err := propositionCapabilityDiagnostics(resource, caps)
		if err != nil {
			return nil, err
		}
		result = append(result, findings...)
	}
	return result, nil
}

func variableName(input string) string {
	if strings.HasPrefix(input, "${") && strings.HasSuffix(input, "}") {
		return strings.TrimSuffix(strings.TrimPrefix(input, "${"), "}")
	}
	return ""
}

func workflowCapabilityDiagnostics(kinds map[string][]processor.Resource, caps orchestratorCapabilities) []diagnostic.Diagnostic {
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termOrchestration, address, message))
	}
	features, predicates := []string{}, []string{}
	usesAssertions := false
	for _, resource := range kinds["workflow"] {
		features = append(features, resource.RequiredFeatures...)
		predicates = append(predicates, resource.WorkflowStatePredicateFeatures...)
		usesAssertions = usesAssertions || resource.UsesAssertionRefs
	}
	for _, resource := range kinds["event"] {
		usesAssertions = usesAssertions || resource.UsesAssertionRefs
	}
	slices.Sort(features)
	features = slices.Compact(features)
	for _, feature := range features {
		if !slices.Contains(caps.SupportedWorkflowFeatures, feature) {
			add("orchestrator.workflow-feature-unsupported", "orchestration.workflows", "Orchestrator does not support workflow feature '"+feature+"'.")
		}
	}
	if usesAssertions && !caps.SupportsAssertionRefs {
		add("orchestrator.assertion-refs-unsupported", "orchestration.assertion-refs", "Orchestrator does not support assertion-gated events or workflow predicates.")
	}
	slices.Sort(predicates)
	predicates = slices.Compact(predicates)
	for _, feature := range predicates {
		if !slices.Contains(caps.SupportedWorkflowStatePredicates, feature) {
			add("orchestrator.step-state-predicate-feature-unsupported", "orchestration.workflows", "Orchestrator does not support workflow state predicate feature '"+feature+"'.")
		}
	}
	return result
}

func propositionCapabilityDiagnostics(resource processor.Resource, caps evaluatorCapabilities) ([]diagnostic.Diagnostic, error) {
	result := []diagnostic.Diagnostic{}
	add := func(code, address, message string) {
		result = append(result, planDiagnostic(code, termEvaluation, address, message))
	}
	facts := resource.Evaluation
	if facts == nil {
		return nil, invalidPlan()
	}
	if !slices.Contains(caps.SupportedPredicateFamilies, facts.PredicateKind) {
		add("evaluator.unsupported-predicate-family", resource.Address, "Evaluator does not support proposition predicate family '"+facts.PredicateKind+"'.")
	}
	if facts.DeferredExpected && !caps.SupportsDeferredExpectedComparison {
		add("evaluator.unsupported-deferred-expected-comparison", resource.Address, "Evaluator does not support comparing a submission against a deferred generated value.")
	}
	if !slices.Contains(caps.SupportedQuantifiers, facts.Quantifier) {
		add("evaluator.unsupported-quantifier", resource.Address, "Evaluator does not support proposition quantifier '"+facts.Quantifier+"'.")
	}
	if len(facts.UnresolvedEvidenceChannelRefs) > 0 {
		add("evaluator.evidence-channel-unresolved", resource.Address, "Evaluator admission requires every cited evidence requirement to declare a channel kind.")
	}
	for _, channel := range facts.EvidenceChannels {
		if !slices.Contains(caps.SupportedEvidenceChannels, channel) {
			add("evaluator.unsupported-evidence-channel", resource.Address, "Evaluator does not support evidence channel '"+channel+"'.")
		}
	}
	if facts.RequiredTimeDomain != "" && !slices.Contains(caps.SupportedTimeDomains, facts.RequiredTimeDomain) {
		add("evaluator.unsupported-time-domain", resource.Address, "Evaluator does not support proposition time domain '"+facts.RequiredTimeDomain+"'.")
	}
	return result, nil
}
