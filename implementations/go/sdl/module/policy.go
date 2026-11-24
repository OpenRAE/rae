package module

import "strings"

// DecodePolicy preserves bounded SafeLoader workspace scalars and closed keys.
func DecodePolicy(raw []byte) (Policy, error) {
	policy := DefaultPolicy()
	if emptyPolicy(raw) {
		return policy, nil
	}
	value, err := workspacePolicy(raw, "raes-trust.yaml")
	if err != nil {
		return Policy{}, err
	}
	if !closedPolicy(value, []string{termSchemaVersion, "allow_unsigned_local_sources", "registries"}) {
		return Policy{}, invalid()
	}
	if version, present := value[termSchemaVersion]; present {
		var ok bool
		policy.SchemaVersion, ok = version.(string)
		if !ok {
			return Policy{}, invalid()
		}
	}
	if flag, present := value["allow_unsigned_local_sources"]; present {
		policy.AllowUnsignedLocalSources, err = policyFlag(flag)
		if err != nil {
			return Policy{}, err
		}
	}
	if raw, exists := value["registries"]; exists {
		if err = decodePolicyRegistries(&policy, raw); err != nil {
			return Policy{}, err
		}
	}
	return policy, nil
}
func decodePolicyRegistries(policy *Policy, raw any) error {
	registries := object(raw)
	if registries == nil {
		return invalid()
	}
	for name, value := range registries {
		rule, err := decodeRegistryTrust(object(value))
		if err != nil {
			return err
		}
		policy.Registries[name] = rule
	}
	return nil
}
func decodeRegistryTrust(value map[string]any) (RegistryTrust, error) {
	rule := RegistryTrust{RequireSignatures: true, TrustedSigners: map[string]string{}}
	if !closedPolicy(value, []string{"require_signatures", "allow_insecure_http", "trusted_signers"}) {
		return rule, invalid()
	}
	var err error
	for field, dest := range map[string]*bool{"require_signatures": &rule.RequireSignatures, "allow_insecure_http": &rule.AllowInsecureHTTP} {
		if raw, exists := value[field]; exists {
			*dest, err = policyFlag(raw)
			if err != nil {
				return rule, err
			}
		}
	}
	if raw, exists := value["trusted_signers"]; exists {
		signers := object(raw)
		if signers == nil {
			return rule, invalid()
		}
		for name, value := range signers {
			key, ok := value.(string)
			if !ok {
				return rule, invalid()
			}
			rule.TrustedSigners[name] = key
		}
	}
	return rule, nil
}
func closedPolicy(value map[string]any, allowed []string) bool {
	if value == nil {
		return false
	}
	for key := range value {
		found := false
		for _, name := range allowed {
			found = found || name == key
		}
		if !found {
			return false
		}
	}
	return true
}
func policyFlag(value any) (bool, error) {
	if flag, ok := value.(bool); ok {
		return flag, nil
	}
	if raw, ok := value.(string); ok {
		switch strings.ToLower(raw) {
		case "true", "t", "yes", "y", "on", "1":
			return true, nil
		case "false", "f", "no", "n", "off", "0":
			return false, nil
		}
	}
	return false, invalid()
}
func emptyPolicy(raw []byte) bool {
	for line := range strings.SplitSeq(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line != "" && !strings.HasPrefix(line, "#") {
			return false
		}
	}
	return true
}

// VersionRequirement is a validated PEP 440 request with private invariants.
type VersionRequirement struct {
	spec  versionRequirement
	valid bool
}

// ParseVersionRequirement admits the existing exact or range compatibility profile.
func ParseVersionRequirement(requested string) (VersionRequirement, error) {
	spec, err := versionSpec(requested)
	if err != nil {
		return VersionRequirement{}, err
	}
	return VersionRequirement{spec: spec, valid: true}, nil
}

// Accepts evaluates an actual version. A zero requirement admits nothing.
func (r VersionRequirement) Accepts(actual string) bool { return r.valid && r.spec.accepts(actual) }
