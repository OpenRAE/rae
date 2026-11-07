package admission

func (r *materializationInventory) preparedSupport(requirement any) error {
	kind := stringAt(requirement, "requirement_kind")
	if kind == "compute-substrate" && stringAt(requirement, "explicitness") == termOpen {
		return nil
	}
	if kind == "process-resource-limits" {
		return r.processLimits(requirement)
	}
	declarations := []any{}
	for _, declaration := range array(at(r.execution.manifest, "realization_support")) {
		if !equal(at(declaration, "domain"), at(requirement, "domain")) {
			continue
		}
		supported := materializationDeclarationSupport(requirement, declaration, kind)
		if supported {
			declarations = append(declarations, declaration)
		}
	}
	if len(declarations) == 0 {
		return invalid()
	}
	if err := materializationSupportObservation(requirement, declarations, kind); err != nil {
		return err
	}
	if artifact := at(requirement, "artifact_requirement"); artifact != nil {
		return materializationArtifactSupport(artifact, declarations, kind)
	}
	return nil
}
func materializationObservation(requirement, capability any) bool {
	if capability == nil {
		return false
	}
	requiredScope, actualScope := stringAt(requirement, "verification_scope"), stringAt(capability, "verification_scope")
	scope := requiredScope == "" || requiredScope == actualScope || requiredScope == "presence" && actualScope == termConfiguration
	requiredSource, actualSource := stringAt(requirement, "required_observation_strength"), stringAt(capability, "observation_strength")
	source := requiredSource == actualSource
	if requiredSource == "" {
		source = actualSource == "daemon-observed" || actualSource == "guest-observed"
	}
	return scope && source
}
func materializationArtifactSupport(artifact any, declarations []any, kind string) error {
	// Inventory admission invokes the established owner without availability facts.
	// Its empty availability context cannot prove immutable bytes or candidates.
	if at(artifact, "exact_artifact") != nil {
		return invalid()
	}
	for _, field := range []string{termConstraints, "locked_inputs", "candidates", "materialization_specifications"} {
		if len(array(at(artifact, field))) > 0 {
			return invalid()
		}
	}
	for _, route := range array(at(artifact, "permitted_routes")) {
		if materializationArtifactRoute(route, declarations, kind) {
			return nil
		}
	}
	return invalid()
}

func materializationDeclarationSupport(requirement, declaration any, kind string) bool {
	mode := stringAt(requirement, "explicitness")
	var supported bool
	switch mode {
	case termOpen:
		supported = stringAt(declaration, "support_mode") == "open-realization"
	case termConstrained:
		supported = set(at(declaration, "supported_constraint_kinds"))[kind]
	case postureExact:
		exact := set(at(declaration, "supported_exact_requirement_kinds"))
		supported = exact["declared-capability-match"] && (!materializationConcernSpecific(kind) || exact[kind])
	default:
		return false
	}
	return supported
}

func materializationSupportObservation(requirement any, declarations []any, kind string) error {
	if at(requirement, "verification_scope") != nil {
		observationKind := kind
		if kind == "os-family" || kind == "os-distribution" || kind == "os-version" {
			observationKind = "operating-system"
		}
		observed := false
		for _, declaration := range declarations {
			observed = observed || materializationObservation(requirement, at(declaration, "observation_capabilities", observationKind))
		}
		if !observed {
			return invalid()
		}
	}
	return nil
}

func materializationArtifactRoute(route any, declarations []any, kind string) bool {
	for _, declaration := range declarations {
		for _, mechanism := range array(at(declaration, "artifact_mechanisms")) {
			if !set(at(mechanism, "supported_requirement_kinds"))[kind] || !matchingFields(at(route, "mechanism"), at(mechanism, "mechanism"), "mechanism", "profile", "version", "digest") {
				continue
			}
			for _, supported := range array(at(mechanism, "supported_routes")) {
				if matchingFields(route, supported, "acquisition", "timing") {
					return true
				}
			}
		}
	}
	return false
}

// Match the native registered runtime concerns; a name prefix is not authority.
func materializationConcernSpecific(kind string) bool {
	switch kind {
	case "runtime-environment", "runtime-mounts", "linux-capabilities",
		"published-ports", "forwarding-agents", "service-listeners",
		"runtime-filesystem-inventory", "runtime-local-control-interfaces", "runtime-processes",
		"runtime-restart-policy", "runtime-node-memory-limit", "runtime-node-memory-swap-limit",
		"runtime-node-cpu-limit", "runtime-node-pids-limit", "runtime-container-entrypoint",
		"runtime-container-command", "runtime-container-log-driver", "runtime-container-log-options",
		"runtime-container-namespaces", "runtime-container-privileged", "runtime-container-read-only-rootfs",
		"runtime-container-publish-all-ports", "runtime-container-autoremove", "runtime-container-shm-size",
		"runtime-container-masked-paths", "runtime-container-read-only-paths", "runtime-container-cgroup-parent",
		"runtime-container-runtime-name", "runtime-container-init-process", "runtime-container-devices",
		"runtime-container-device-cgroup-rules", "runtime-container-seccomp-profile", "runtime-container-security-opt",
		"runtime-container-extra-hosts", "runtime-container-dns", "runtime-container-dns-options",
		"runtime-container-dns-search", "runtime-container-group-add", "runtime-local-identity",
		"runtime-identity-authorities", "runtime-file-services", "runtime-mail-services",
		"runtime-network-hostname", "runtime-network-domainname", "runtime-network-endpoints",
		"runtime-applications", "runtime-database-services", "runtime-dns-services",
		"runtime-network-sensors", "runtime-network-detection-engines", "runtime-security-monitoring-managers",
		"runtime-ssh-servers", "runtime-datastore-services", "runtime-platform-applications",
		"runtime-orchestration-authorities", "runtime-app-authorizations", "runtime-scheduled-jobs",
		"runtime-service-manager-units", "runtime-packages", "runtime-repository-state",
		"runtime-software-components", "runtime-dependency-manifests":
		return true
	default:
		return false
	}
}
