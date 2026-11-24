package authoring

import (
	"encoding/json"
	"fmt"
	"math/big"
	"slices"
)

// semanticInteger preserves the integer/string/null union without float64.
type semanticInteger struct {
	integer  *big.Int
	variable string
}

func (number *semanticInteger) UnmarshalJSON(raw []byte) error {
	*number = semanticInteger{}
	if string(raw) == nullType {
		return nil
	}
	if len(raw) > 0 && raw[0] == '"' {
		if json.Unmarshal(raw, &number.variable) != nil {
			return invalid()
		}
		return nil
	}
	integer, valid := modelInteger(json.Number(raw))
	if !valid {
		return invalid()
	}
	number.integer = integer
	return nil
}
func (number semanticInteger) active() bool {
	return number.integer != nil || number.variable != ""
}
func (number semanticInteger) equal(other semanticInteger) bool {
	if !number.active() || !other.active() {
		return !number.active() && !other.active()
	}
	if number.integer != nil {
		return other.integer != nil && number.integer.Cmp(other.integer) == 0
	}
	return number.variable != "" && number.variable == other.variable
}

type semanticProcessIdentity struct {
	Name      string          `json:"name"`
	PID       semanticInteger `json:"pid"`
	Parent    semanticInteger `json:"parent_pid"`
	Command   []string        `json:"command"`
	Redacted  json.RawMessage `json:"command_redacted"`
	Role      string          `json:"role"`
	User      string          `json:"user"`
	Group     string          `json:"group"`
	Directory string          `json:"working_directory"`
}
type semanticRuntimeCapabilities struct {
	Overrides []struct {
		Subject semanticProcessIdentity `json:"subject"`
	} `json:"process_overrides"`
}
type semanticRuntimeOperationalPolicy struct {
	Resources *struct {
		Limits []struct {
			Subject semanticProcessIdentity `json:"subject"`
		} `json:"process_limits"`
	} `json:"resource_limits"`
}

func (selector semanticProcessIdentity) matches(candidate semanticProcessIdentity) bool {
	for _, field := range [][2]string{{selector.Name, candidate.Name}, {selector.User, candidate.User}, {selector.Group, candidate.Group}, {selector.Directory, candidate.Directory}} {
		if field[0] != "" && field[0] != field[1] {
			return false
		}
	}
	if selector.PID.active() && !selector.PID.equal(candidate.PID) {
		return false
	}
	if selector.Parent.active() && !selector.Parent.equal(candidate.Parent) {
		return false
	}
	if len(selector.Command) > 0 && !slices.Equal(selector.Command, candidate.Command) {
		return false
	}
	if string(selector.Redacted) == trueTerm && string(candidate.Redacted) != trueTerm {
		return false
	}
	role := selector.Role
	if role != "" && role != otherTerm && role != processRole(candidate) {
		return false
	}
	return true
}
func processRole(process semanticProcessIdentity) string {
	if process.Role == "" {
		return otherTerm
	}
	return process.Role
}
func (m *semanticModel) checkRuntimeCapabilities(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil || node.runtime.Capabilities == nil {
			continue
		}
		observed := map[string]bool{}
		for _, process := range node.runtime.Processes {
			if process.Name != "" && !variable(process.Name) {
				observed[process.Name] = true
			}
		}
		if len(observed) == 0 {
			continue
		}
		check := semanticRuntimeCheck{m, c, node}
		check.capabilitySubjects(observed)
	}
}
func (r semanticRuntimeCheck) capabilitySubjects(observed map[string]bool) {
	for _, override := range r.node.runtime.Capabilities.Overrides {
		name := override.Subject.Name
		if name != "" && !variable(name) && !observed[name] {
			r.reportf("Node '"+r.node.name+"' runtime capability override", "subject '%s' does not match any process declared in 'runtime.processes'", name)
		}
	}
}
func (m *semanticModel) checkRuntimeProcessLimits(c *semanticCollector) {
	for _, node := range m.nodes {
		if node.runtime == nil || node.runtime.Policy == nil || node.runtime.Policy.Resources == nil {
			continue
		}
		for _, limit := range node.runtime.Policy.Resources.Limits {
			if !slices.ContainsFunc(node.runtime.Processes, limit.Subject.matches) {
				c.report(semanticOwner{nodesSection, node.name}, fmt.Sprintf("Node '%s' runtime process resource limit subject does not match any process declared in 'runtime.processes'", node.name))
			}
		}
	}
}
