package authoring

import "strings"

const cloudReferencePaths = `
nodes/*/runtime/identity_authorities/*/resource_scopes/*/parent_ref
nodes/*/runtime/identity_authorities/*/subjects/*/resource_scope_ref
nodes/*/runtime/identity_authorities/*/identity_uses/*/workload_ref
nodes/*/runtime/identity_authorities/*/identity_uses/*/principal_ref
nodes/*/runtime/identity_authorities/*/identity_uses/*/source_principal_ref
nodes/*/runtime/identity_authorities/*/policies/*/resource_access/attachment_ref
nodes/*/runtime/identity_authorities/*/policies/*/resource_access/inherited_from_ref
nodes/*/runtime/identity_authorities/*/policies/*/resource_access/bindings/*/role_ref
nodes/*/runtime/identity_authorities/*/policies/*/resource_access/bindings/*/principal_refs
nodes/*/runtime/identity_authorities/*/policies/*/resource_access/bindings/*/resource_refs
nodes/*/runtime/identity_authorities/*/access_observations/*/principal_ref
nodes/*/runtime/identity_authorities/*/access_observations/*/resource_ref
nodes/*/runtime/identity_authorities/*/access_observations/*/context_refs
nodes/*/runtime/platform_applications/*/resource_scope_ref
nodes/*/runtime/platform_applications/*/cloud_limits/*/resource_scope_ref
nodes/*/runtime/platform_applications/*/secrets/*/resource_scope_ref
nodes/*/runtime/platform_applications/*/secrets/*/encryption_key_ref
nodes/*/runtime/platform_applications/*/secrets/*/reset_owner_ref
nodes/*/runtime/platform_applications/*/secrets/*/deletion_owner_ref
nodes/*/runtime/platform_applications/*/secrets/*/versions/*/payload_content_ref
nodes/*/runtime/platform_applications/*/secrets/*/consumers/*/consumer_ref
nodes/*/runtime/platform_applications/*/secrets/*/consumers/*/version_ref
nodes/*/runtime/platform_applications/*/secrets/*/consumers/*/resolved_version_ref
`

func rewriteCloudReferences(value map[string]any, symbols importSymbols) error {
	for line := range strings.SplitSeq(cloudReferencePaths, "\n") {
		if line == "" {
			continue
		}
		if _, err := rewritePath(value, strings.Split(line, "/"), symbols, termNamed); err != nil {
			return err
		}
	}
	return nil
}
