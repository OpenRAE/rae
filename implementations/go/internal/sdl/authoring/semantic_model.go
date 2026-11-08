package authoring

import (
	"encoding/json"
	"fmt"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
)

// The semantic model contains ordered, typed facts, independent of transport
// serialization. Schema construction has already checked their local shapes.
type semanticModel struct {
	intent             *semanticIntentVisitor
	variationConsumers map[semanticOwner][]semanticConsumerSelector
	root               map[string]any
	probeCache         map[semanticVariationCandidate]bool
	variations         []semanticVariation
	variationVariables map[string]semanticVariationVariable
	policies           semanticPolicies
	boundaryRules      map[string][]semanticBoundaryRule
	timeCoordinates    map[string]semanticInterval
	behaviorIndex      map[string]int
	localOutcomes      map[string]semanticLocalOutcome
	controlAssets      map[string]semanticControlAsset
	controlOwners      []semanticControlOwner
	temporal           []sdlrules.Finding
	cadenceValues      map[string]semanticCadence
	nodes              []semanticNode
	features           []semanticFeature
	definitions        map[string]map[string]bool
	transport          binding.SdlAuthoringInputV1
	document           *Document
	nodeIndex          map[string]int
	infrastructure     []semanticInfrastructure
	order              map[string][]string
	index              *declarationIndex
	accounts           []semanticAccount
	entities           []semanticEntityFact
	entityNames        map[string]bool
	relationships      []semanticRelationship
	objectives         []semanticObjective
	scopes             *scopeQueries
	evidence           []semanticEvidence
	forwarders         []semanticForwarder
	execution          *semanticExecutionDocument
	workflows          []semanticWorkflow
	parser             *Parser
	descriptors        []semanticDescriptor
	agents             []semanticAgent
	operating          *declarationIndex
	stateful           []sdlrules.Finding
	serviceContent     map[string][]sdlrules.Finding
	behaviors          []semanticBehavior
	roles              map[string]string
}
type semanticNode struct {
	serviceDetails          map[string]semanticService
	paths                   map[string]bool
	runtime                 *semanticRuntime
	name, kind              string
	bindings                []semanticBinding
	roles                   map[string]bool
	resources               bool
	os, distribution        bool
	osVersion, architecture string
	packages                []semanticPackage
	roleDefinitions         []semanticRole
	services                []string
	persona                 string
}
type semanticBinding struct{ section, name, role string }
type semanticFeature struct {
	name         string
	dependencies []string
}

func (p *Parser) newSemanticModel(document *Document) (*semanticModel, error) {
	var transport binding.SdlAuthoringInputV1
	if err := json.Unmarshal(document.modelBytes(), &transport); err != nil {
		return nil, invalid()
	}
	model := &semanticModel{parser: p, definitions: map[string]map[string]bool{}, transport: transport, document: document, nodeIndex: map[string]int{}}
	var err error
	model.order, err = semanticOrder(document.modelBytes())
	if err != nil {
		return nil, err
	}
	value, err := ingress.Parse(document.modelBytes(), modelLimits(document.modelBytes()), ingress.Object)
	if err != nil {
		return nil, err
	}
	model.index = orderedDeclarations(object(value), model.order)
	model.root = object(value)
	model.operating = operatingScopeIndex(object(value))
	model.scopes = newScopeQueries(p, document.contract, object(value))
	model.definitionsFromOrder()
	for _, load := range []func() error{model.variationFacts, model.policyFacts, model.nodeFacts, model.infrastructureFacts, model.accountFacts, model.entityFacts, model.objectiveFacts, model.evidenceFacts, model.executionFacts, model.descriptorFacts, model.agentFacts, model.behaviorFacts, model.cadenceFacts, model.controlFacts, model.outcomeFacts, model.boundaryRuleFacts} {
		if loadErr := load(); loadErr != nil {
			return nil, loadErr
		}
	}
	model.roles = model.effectiveRoles()
	model.relationships, err = model.relationshipFacts()
	if err != nil {
		return nil, err
	}
	model.stateful, err = sdlrules.StatefulReferences(document.modelBytes(), model.order)
	if err != nil {
		return nil, err
	}
	serviceFindings, serviceErr := sdlrules.ServiceMaterialization(document.modelBytes(), model.order)
	if serviceErr != nil {
		return nil, serviceErr
	}
	model.temporal, err = sdlrules.TemporalBindings(document.modelBytes(), model.order)
	if err != nil {
		return nil, err
	}
	model.serviceContent = map[string][]sdlrules.Finding{}
	for _, finding := range serviceFindings {
		model.serviceContent[finding.Owner.Name] = append(model.serviceContent[finding.Owner.Name], finding)
	}
	features := fieldValue(transport.Features)
	for _, name := range model.keys(featuresSection) {
		model.features = append(model.features, semanticFeature{name, fieldValue(features[name].Dependencies)})
	}
	return model, nil
}
func (m *semanticModel) definitionsFromOrder() {
	for _, section := range declarationSections() {
		m.definitions[section] = map[string]bool{}
		for _, name := range m.keys(section) {
			m.definitions[section][name] = true
		}
	}
}
func (m *semanticModel) nodeFacts() error {
	for _, name := range m.keys(nodesSection) {
		node, err := m.nodeFact(name)
		if err != nil {
			return err
		}
		m.nodeIndex[name] = len(m.nodes)
		m.nodes = append(m.nodes, node)
	}
	return nil
}
func (m *semanticModel) nodeFact(name string) (semanticNode, error) {
	raw := fieldValue(m.transport.Nodes)[name]
	resources := fieldValue(raw.Resources)
	node := semanticNode{name: name, kind: string(fieldValue(raw.Type)), resources: len(resources) != 0 && string(resources) != nullType, roles: map[string]bool{}}
	var err error
	if loadErr := m.nodeRuntimeFacts(name, &node); loadErr != nil {
		return semanticNode{}, loadErr
	}
	node.os, node.distribution = raw.Os.Present() && !raw.Os.Null(), raw.OsDistribution.Present() && !raw.OsDistribution.Null()
	node.osVersion = fieldValue(raw.OsVersion)
	node.architecture, err = scalarText(fieldValue(raw.Architecture), "")
	if err != nil {
		return semanticNode{}, err
	}
	node.persona, err = scalarText(fieldValue(raw.EndpointPersona), "")
	if err != nil {
		return semanticNode{}, err
	}
	node.packages, err = semanticPackages(fieldValue(raw.Runtime))
	if err != nil {
		return semanticNode{}, err
	}
	if serviceErr := m.nodeServiceFacts(name, &node); serviceErr != nil {
		return semanticNode{}, serviceErr
	}
	node.roleDefinitions, err = m.roleFacts(name, fieldValue(raw.Roles))
	if err != nil {
		return semanticNode{}, err
	}
	for name := range fieldValue(raw.Roles) {
		node.roles[name] = true
	}
	for _, section := range []struct {
		name   string
		values map[string]string
	}{
		{featuresSection, fieldValue(raw.Features)}, {conditionsSection, fieldValue(raw.Conditions)}, {injectsSection, fieldValue(raw.Injects)},
	} {
		for _, ref := range m.keys(nodesSection, name, section.name) {
			node.bindings = append(node.bindings, semanticBinding{section.name, ref, section.values[ref]})
		}
	}
	return node, nil
}
func semanticPackages(raw json.RawMessage) ([]semanticPackage, error) {
	if len(raw) == 0 || string(raw) == nullType {
		return nil, nil
	}
	var inventory struct {
		Packages []semanticPackage `json:"packages"`
		Software []struct {
			Presence string           `json:"presence"`
			Package  *semanticPackage `json:"package"`
		} `json:"software_components"`
	}
	if err := json.Unmarshal(raw, &inventory); err != nil {
		return nil, invalid()
	}
	result := inventory.Packages
	for _, component := range inventory.Software {
		if component.Presence != "forbidden" && component.Package != nil {
			result = append(result, *component.Package)
		}
	}
	return result, nil
}

func (m *semanticModel) keys(tokens ...string) []string {
	return m.order[jsonpointer.FromTokens(tokens)]
}

func (m *semanticModel) check(c *semanticCollector) error {
	for _, message := range m.index.collisions {
		c.report(semanticOwner{}, message)
	}
	m.checkNodes(c)
	m.checkInfrastructure(c)
	m.checkRuntimeNetwork(c)
	m.checkRuntimeSensors(c)
	m.checkRuntimeDetection(c)
	m.checkRuntimeListeners(c)
	m.checkRuntimeApplications(c)
	m.checkRuntimeCapabilities(c)
	m.checkRuntimeProcessLimits(c)
	m.checkRuntimeDatabases(c)
	m.checkRuntimeDNS(c)
	m.checkRuntimeSSH(c)
	m.checkRuntimeAuthorizations(c)
	m.checkRuntimeServiceUnits(c)
	m.checkRuntimeIdentityAuthorities(c)
	m.checkRuntimeFiles(c)
	m.checkRuntimeMonitoring(c)
	m.checkRuntimeDatastores(c)
	m.checkRuntimePlatforms(c)
	m.checkRuntimeForwarding(c)
	m.checkRuntimeOrchestration(c)
	m.checkRuntimeMail(c)
	m.checkCloudResources(c)
	m.checkRuleSourceGenerators(c)
	m.checkFeatures(c)
	m.checkNarrative(c)
	m.checkStatefulResources(c)
	m.checkContentAndAccounts(c)
	m.checkRelationships(c)
	m.checkTopology(c)
	m.checkEnterpriseIdentity(c)
	m.checkDescriptorProfiles(c)
	m.checkTenancy(c)
	m.checkRelationshipDatabases(c)
	m.checkRelationshipMail(c)
	m.checkRelationshipForwarding(c)
	m.checkRelationshipIntegrations(c)
	m.checkRelationshipProxy(c)
	m.checkAgents(c)
	m.checkInteractiveAccess(c)
	m.checkParticipantBehavior(c)
	m.checkPropositions(c)
	m.checkObjectives(c)
	m.checkObjectiveAssertionRoles(c)
	m.checkPreconditionAssertionUses(c)
	m.checkWorkflows(c)
	m.checkOutcomes(c)
	m.checkEvidence(c)
	m.checkAugmentation(c)
	m.checkExecution(c)
	m.checkTime(c)
	if err := m.checkVariables(c); err != nil {
		return err
	}
	if err := m.checkVariations(c); err != nil {
		return err
	}
	m.checkRealization(c)
	m.checkExplicitness(c)
	for _, node := range m.nodes {
		if node.kind == "compute" && !node.resources {
			c.missingResources(node.name)
		}
	}
	return nil
}

func (m *semanticModel) checkNodes(c *semanticCollector) {
	for _, node := range m.nodes {
		local := node.name[strings.LastIndexByte(node.name, '.')+1:]
		if utf8.RuneCountInString(local) > 35 {
			c.report(semanticOwner{nodesSection, node.name}, fmt.Sprintf("Node '%s' name exceeds 35 characters", node.name))
		}
		m.checkNodeBindings(c, node)
		checkNodePlatform(c, node)
	}
}
func (m *semanticModel) checkNodeBindings(c *semanticCollector, node semanticNode) {
	owner := semanticOwner{nodesSection, node.name}
	for _, reference := range node.bindings {
		kind := strings.TrimSuffix(reference.section, "s")
		if !m.definitions[reference.section][reference.name] {
			c.report(owner, fmt.Sprintf("Node '%s' references undefined %s '%s'", node.name, kind, reference.name))
		}
		if reference.role != "" && !variable(reference.role) && !node.roles[reference.role] {
			c.report(owner, fmt.Sprintf("Node '%s' %s '%s' references undefined role '%s'", node.name, kind, reference.name, reference.role))
		}
	}
}
func checkNodePlatform(c *semanticCollector, node semanticNode) {
	owner := semanticOwner{nodesSection, node.name}
	if node.distribution && !node.os {
		c.report(owner, fmt.Sprintf("Node '%s' OS distribution requires an OS family", node.name))
	}
	if node.osVersion != "" && !node.distribution {
		c.report(owner, fmt.Sprintf("Node '%s' OS version requires an OS distribution", node.name))
	}
	for _, pkg := range node.packages {
		checkPackageArchitecture(c, node, pkg)
	}
}
func checkPackageArchitecture(c *semanticCollector, node semanticNode, pkg semanticPackage) {
	if pkg.Architecture == "" || variable(pkg.Architecture) {
		return
	}
	owner := semanticOwner{nodesSection, node.name}
	if node.architecture == "" {
		c.report(owner, fmt.Sprintf("Node '%s' package '%s' declares architecture '%s' but the node declares no target architecture; package metadata must not imply a target-node architecture", node.name, pkg.Name, pkg.Architecture))
	} else if !variable(node.architecture) && node.architecture != pkg.Architecture {
		c.report(owner, fmt.Sprintf("Node '%s' target architecture '%s' is incompatible with package '%s' architecture '%s'", node.name, node.architecture, pkg.Name, pkg.Architecture))
	}
}

type semanticPackage struct {
	Name         string `json:"name"`
	Architecture string `json:"architecture"`
}

func (m *semanticModel) checkFeatures(c *semanticCollector) {
	dependencies := map[string][]string{}
	for _, feature := range m.features {
		for _, reference := range feature.dependencies {
			if variable(reference) {
				continue
			}
			if !m.definitions[featuresSection][reference] {
				c.report(semanticOwner{featuresSection, feature.name}, fmt.Sprintf("Feature '%s' depends on undefined feature '%s'", feature.name, reference))
			} else {
				dependencies[feature.name] = append(dependencies[feature.name], reference)
			}
		}
	}
	if graph.HasCycle(dependencies) {
		c.report(semanticOwner{}, "Feature dependency graph contains a cycle")
	}
}
