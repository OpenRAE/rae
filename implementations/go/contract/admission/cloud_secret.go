package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

const (
	replicationAutomatic   = "automatic"
	replicationUserManaged = "user-managed"
)

func (e *Validator) cloudSecretRules() map[string]definition {
	return map[string]definition{
		"cloud-audit-scope-uniqueness":          {check: auditScopeUniqueness},
		"secret-replication-location-agreement": {check: secretReplicationAgreement},
	}
}

// auditScopeUniqueness refuses a repeated audit log id or service and log type pair in one resource scope.
func auditScopeUniqueness(i validation.Invocation) error {
	logs := array(at(i.Instance, "audit_logs"))
	return require(len(rowSet(logs, "audit_log_id")) == len(logs) && len(rowTupleSet(logs, "service", "log_type")) == len(logs))
}

// secretReplicationAgreement checks the replica set and the encryption key locations of one replication policy.
func secretReplicationAgreement(i validation.Invocation) error {
	v := i.Instance
	replicas := array(at(v, "replicas"))
	mode := stringAt(v, "mode")
	if mode == replicationAutomatic && (len(replicas) > 0 || !keyLocationMatches(at(v, "kms_key_name"), "global")) {
		return invalid()
	}
	if mode == replicationUserManaged && (len(replicas) == 0 || at(v, "kms_key_name") != nil) {
		return invalid()
	}
	seen := map[string]bool{}
	for _, replica := range replicas {
		location := stringAt(replica, "location")
		if !keyLocationMatches(at(replica, "kms_key_name"), location) {
			return invalid()
		}
		if variableRef(location) {
			continue
		}
		if seen[location] {
			return invalid()
		}
		seen[location] = true
	}
	return nil
}

// keyLocationMatches reports whether a Cloud KMS key name uses the location.
// An absent key or a variable key or location is not compared.
func keyLocationMatches(key any, location string) bool {
	name, ok := key.(string)
	if !ok || variableRef(name) || variableRef(location) {
		return true
	}
	parts := strings.Split(name, "/")
	return len(parts) > 3 && parts[3] == location
}
