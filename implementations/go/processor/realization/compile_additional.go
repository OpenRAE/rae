package realization

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func (s *realizationSource) compileOtherRequirements(result *Resolution) error {
	if err := s.compileTopologyRequirements(result); err != nil {
		return err
	}
	for _, item := range []struct{ section, kind string }{{"generated_artifacts", "generated-artifact"}, {"persistent_volumes", "persistent-volume"}} {
		for _, name := range s.sections[item.section].names {
			resource, err := address.Render("provision", item.kind, name)
			if err != nil {
				return err
			}
			requirement := exactRequirement(resource, item.section+"."+name, item.kind, termAuthorDeclared, "#"+jsonpointer.FromTokens([]string{item.section, name}))
			result.Requirements = append(result.Requirements, requirement)
		}
	}
	if err := s.compileServiceRequirements(result); err != nil {
		return err
	}

	if err := s.compileSourceArtifactRequirements(result); err != nil {
		return err
	}
	// These concerns have no registered authored leaf but still carry exact
	// processor-derived operational authority for their published payload path.
	for _, requirement := range result.Requirements {
		payload := derivedConcernPayload(requirement.Kind)
		if payload == nil {
			continue
		}
		result.Authority = append(result.Authority, Authority{Address: requirement.Address, FieldPath: requirement.FieldPath, Concern: requirement.Kind, Posture: termExact, Provenance: requirement.Provenance, Domain: requirement.Domain, Source: termProcessorDerived, GoverningScope: requirement.GoverningScope, PayloadPath: payload})
	}
	return nil
}

func exactRequirement(resource, path, kind, provenance, scope string) Requirement {
	posture := termExact
	return Requirement{Address: resource, FieldPath: path, Kind: kind, Domain: termRuntimeRealization, Posture: &posture, Provenance: provenance, GoverningScope: scope, ValueConstraints: []ValueConstraint{}, ProcessResourceLimits: []ProcessResourceLimit{}}
}

func (s *realizationSource) compileSourceArtifactRequirements(result *Resolution) error {
	if err := s.compileResourceSourceArtifactRequirements(result); err != nil {
		return err
	}

	if err := s.compileBoundSourceArtifactRequirements(result); err != nil {
		return err
	}

	for _, item := range []struct{ section, kind string }{{"injects", "inject"}, {"events", "event"}} {
		for _, name := range s.sections[item.section].names {
			resource, err := address.Render("orchestration", item.kind, name)
			if err != nil {
				return err
			}
			if err := s.appendSourceArtifact(result, item.section, name, resource); err != nil {
				return err
			}
		}
	}
	return nil
}

func (s *realizationSource) appendSourceArtifact(result *Resolution, section, name, resource string) error {
	value, err := sourceConcernValue(s.sections[section].values[name], []string{termSource})
	if err != nil {
		return err
	}
	source, ok := value.(map[string]any)
	if !ok || source["artifact_requirement"] == nil {
		return nil
	}
	requirement, ok := source["artifact_requirement"].(map[string]any)
	if !ok {
		return invalidRealization()
	}
	posture, ok := requirement["explicitness"].(string)
	if !ok {
		return invalidRealization()
	}
	encoded, err := json.Marshal(map[string]any{termSchemaVersion: "artifact-requirement/v1", termSource: source})
	if err != nil {
		return invalidRealization()
	}
	var artifact binding.ArtifactRequirementV1
	if json.Unmarshal(encoded, &artifact) != nil {
		return invalidRealization()
	}
	path := section + "." + name + ".source.artifact_requirement"
	scope := "#" + jsonpointer.FromTokens([]string{section, name, termSource, "artifact_requirement"})
	entry := exactRequirement(resource, path, "source-artifact", termAuthorDeclared, scope)
	entry.Posture = &posture
	entry.ArtifactRequirement = &artifact
	result.Requirements = append(result.Requirements, entry)
	return nil
}
func (s *realizationSource) compileBoundSourceArtifactRequirements(result *Resolution) error {
	for _, nodeName := range s.sections[termNodes].names {
		node := sourceValue(s.model.Nodes)[nodeName]
		if err := s.compileBoundSourceArtifacts(result, nodeName, "features", "provision", "feature", sourceValue(node.Features)); err != nil {
			return err
		}
		if err := s.compileBoundSourceArtifacts(result, nodeName, "conditions", "evaluation", "condition", sourceValue(node.Conditions)); err != nil {
			return err
		}
	}
	return nil
}

func (s *realizationSource) sectionName(ref, section string) string {
	if _, exists := s.sections[section].values[ref]; exists {
		return ref
	}
	return strings.TrimPrefix(ref, section+".")
}

func (s *realizationSource) compileTopologyRequirements(result *Resolution) error {
	bindings := s.topologyNodeBindings()
	appendTopology := func(resource, domain string) {
		result.Requirements = append(result.Requirements, exactRequirement(resource, "identity_domains."+domain+".topology", "domain-topology", termProcessorDerived, ""))
	}
	for _, binding := range bindings {
		resource, err := address.Render("provision", termNode, binding.node)
		if err != nil {
			return err
		}
		appendTopology(resource, binding.domain)
	}
	accountDomains, accountOrder := s.topologyAccountDomains()

	for _, name := range accountOrder {
		resource, err := address.Render("provision", "account", name)
		if err != nil {
			return err
		}
		appendTopology(resource, accountDomains[name])
	}

	for _, binding := range bindings {
		if binding.role == "controller" {
			resource, err := address.Render("provision", "domain-controller", binding.domain, binding.node)
			if err != nil {
				return err
			}
			appendTopology(resource, binding.domain)
		}
	}
	return nil
}

type nodeBinding struct{ node, domain, role string }

func (s *realizationSource) topologyNodeBindings() []nodeBinding {
	controllers, joins := s.topologyRelationships()
	bindings := []nodeBinding{}
	seen := map[string]bool{}
	for _, domain := range s.sections["identity_domains"].names {
		for _, node := range controllers[domain] {
			if !seen[node] {
				bindings = append(bindings, nodeBinding{node, domain, "controller"})
				seen[node] = true
			}
		}
	}
	for _, binding := range joins {
		if !seen[binding.node] {
			bindings = append(bindings, binding)
			seen[binding.node] = true
		}
	}
	return bindings
}
func (s *realizationSource) topologyAccountDomains() (map[string]string, []string) {
	accounts := sourceValue(s.model.Accounts)
	accountDomains := map[string]string{}
	accountOrder := []string{}
	for _, name := range s.sections["accounts"].names {
		if ref := sourceValue(accounts[name].DomainRef); ref != "" {
			accountDomains[name] = s.sectionName(ref, "identity_domains")
			accountOrder = append(accountOrder, name)
		}
	}
	domains := sourceValue(s.model.IdentityDomains)
	for _, name := range s.sections["identity_domains"].names {
		ref := sourceValue(domains[name].AuthorityAccountRef)
		if ref == "" {
			continue
		}
		account := s.sectionName(ref, "accounts")
		if _, exists := accountDomains[account]; !exists {
			accountOrder = append(accountOrder, account)
		}
		accountDomains[account] = name
	}
	return accountDomains, accountOrder
}

func (s *realizationSource) compileResourceSourceArtifactRequirements(result *Resolution) error {
	for _, section := range []string{termNodes, termContent} {
		for _, name := range s.sections[section].names {
			resource, err := s.resourceAddress(section, name)
			if err != nil {
				return err
			}
			if err := s.appendSourceArtifact(result, section, name, resource); err != nil {
				return err
			}
		}
	}
	return nil
}

func (s *realizationSource) compileBoundSourceArtifacts(result *Resolution, node, section, domain, kind string, names map[string]string) error {
	for _, name := range s.fieldOrder[jsonpointer.FromTokens([]string{termNodes, node, section})] {
		if _, present := names[name]; !present {
			continue
		}
		resource, err := address.Render(domain, kind, node, name)
		if err != nil {
			return err
		}
		if err := s.appendSourceArtifact(result, section, name, resource); err != nil {
			return err
		}
	}
	return nil
}

func (s *realizationSource) compileServiceRequirements(result *Resolution) error {
	for _, name := range s.sections[termContent].names {
		value, err := sourceConcernValue(s.sections[termContent].values[name], []string{termServiceMaterialization})
		if err != nil {
			return err
		}
		profile, ok := value.(map[string]any)
		if !ok || profile["interface_profile"] == nil {
			continue
		}
		kind := "service-content-materialization"
		if profile["interface_profile"] == "service-search-index-schema" {
			kind = "service-search-index-schema-materialization"
		}
		resource, err := s.resourceAddress(termContent, name)
		if err != nil {
			return err
		}
		result.Requirements = append(result.Requirements, exactRequirement(resource, "content."+name+".service_materialization", kind, termAuthorDeclared, "#"+jsonpointer.FromTokens([]string{termContent, name, termServiceMaterialization})))
	}
	return nil
}

func (s *realizationSource) topologyRelationships() (map[string][]string, []nodeBinding) {
	controllers := map[string][]string{}
	joins := []nodeBinding{}
	relationships := sourceValue(s.model.Relationships)
	for _, name := range s.sections["relationships"].names {
		relation := relationships[name]
		kind := string(sourceValue(relation.Type))
		if kind != "domain_controller_for" && kind != "joins_domain" {
			continue
		}
		node, domain := s.sectionName(sourceValue(relation.Source), termNodes), s.sectionName(sourceValue(relation.Target), "identity_domains")
		if kind == "domain_controller_for" {
			controllers[domain] = append(controllers[domain], node)
		} else {
			joins = append(joins, nodeBinding{node, domain, "member"})
		}
	}

	return controllers, joins
}
