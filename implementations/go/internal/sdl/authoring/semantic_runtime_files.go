package authoring

import (
	"fmt"
	"strings"
)

type semanticFileService struct {
	ID      string `json:"file_service_id"`
	Service string `json:"service"`
	Shares  []struct {
		ID string `json:"share_id"`
	} `json:"shares"`
	Principals []semanticFilePrincipal `json:"principals"`
	Rules      []struct {
		ID       string `json:"rule_id"`
		Subject  string `json:"subject_ref"`
		Resource string `json:"resource_ref"`
	} `json:"access_rules"`
	Observations []struct {
		ID       string `json:"observation_id"`
		Subject  string `json:"subject_ref"`
		Resource string `json:"resource_ref"`
	} `json:"access_observations"`
}
type semanticFilePrincipal struct {
	ID        string `json:"principal_id"`
	User      string `json:"local_user_ref"`
	Directory string `json:"directory_subject_ref"`
}

func (m *semanticModel) checkRuntimeFiles(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		for _, service := range node.runtime.Files {
			check.fileService(service, node.runtime.localUsers())
		}
	}
}
func (r semanticRuntimeCheck) fileService(service semanticFileService, users map[string]bool) {
	label := fmt.Sprintf("Node '%s' runtime file service '%s'", r.node.name, service.ID)
	r.ownedService(label, service.Service)
	shares, subjects := map[string]bool{}, map[string]bool{"anonymous": true, "guest": true}
	for _, share := range service.Shares {
		shares[share.ID] = true
	}
	for _, principal := range service.Principals {
		subjects[principal.ID] = true
		r.filePrincipal(label+" principal '"+principal.ID+"'", principal, users)
	}
	for _, rule := range service.Rules {
		r.fileAccess(label+" rule '"+rule.ID+"'", rule.Subject, rule.Resource, subjects, shares)
	}
	for _, observation := range service.Observations {
		r.fileAccess(label+" observation '"+observation.ID+"'", observation.Subject, observation.Resource, subjects, shares)
	}
}
func (r semanticRuntimeCheck) filePrincipal(label string, principal semanticFilePrincipal, users map[string]bool) {
	if concreteReference(principal.User) && len(users) > 0 && !users[principal.User] {
		r.reportf(label, "local_user_ref '%s' does not resolve to a runtime.local_identity user", principal.User)
	}
	ref := principal.Directory
	if !concreteReference(ref) {
		return
	}
	if !strings.HasPrefix(ref, nodesPrefix) {
		r.reportf(label, "directory_subject_ref '%s' must be a qualified 'nodes.<node>.runtime.identity_authorities.<id>.subjects.<id>' reference", ref)
		return
	}
	entry, present := r.model.index.declarations[ref]
	if !present || entry.kind != "identity_authorities.subjects" {
		r.reportf(label, "directory_subject_ref '%s' does not resolve to a known identity-authority subject", ref)
	}
}
func (r semanticRuntimeCheck) fileAccess(label, subject, resource string, subjects, shares map[string]bool) {
	if concreteReference(subject) && !subjects[subject] {
		r.reportf(label, "subject_ref '%s' does not resolve inside file service", subject)
	}
	if concreteReference(resource) {
		share, _, _ := strings.Cut(resource, ":")
		if !shares[share] {
			r.reportf(label, "resource_ref '%s' does not resolve to a share in the file service", resource)
		}
	}
}
