package authoring

import (
	"encoding/json"
	"math/big"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type semanticExecutionDocument struct {
	Default *semanticExecutionPolicy `json:"default"`
	Scopes  []semanticExecutionScope `json:"scopes"`
}
type semanticExecutionPolicy struct {
	Clock    *string  `json:"clock_ref"`
	Evidence []string `json:"evidence_refs"`
	Retry    struct {
		Attempts json.Number `json:"max_attempts"`
	} `json:"retry"`
}
type semanticExecutionScope struct {
	Namespace []string                `json:"namespace"`
	Scope     string                  `json:"scope"`
	Policy    semanticExecutionPolicy `json:"policy"`
}
type semanticWorkflow struct {
	name, start string
	steps       map[string]semanticWorkflowStep
	order       []string
}
type semanticWorkflowStep struct {
	Type         string                     `json:"type"`
	Attempts     json.RawMessage            `json:"max_attempts"`
	Objective    string                     `json:"objective"`
	Workflow     string                     `json:"workflow"`
	Success      string                     `json:"on_success"`
	Failure      string                     `json:"on_failure"`
	Exhausted    string                     `json:"on_exhausted"`
	Compensation string                     `json:"compensate_with"`
	Next         string                     `json:"next"`
	Then         string                     `json:"then"`
	Else         string                     `json:"else"`
	Default      string                     `json:"default"`
	Join         string                     `json:"join"`
	Branches     []string                   `json:"branches"`
	When         *semanticWorkflowPredicate `json:"when"`
	Cases        []struct {
		When semanticWorkflowPredicate `json:"when"`
		Next string                    `json:"next"`
	} `json:"cases"`
	Procedure    string   `json:"procedure_ref"`
	Scaffolds    []string `json:"scaffold_refs"`
	Actions      []string `json:"allowed_action_families"`
	Tools        []string `json:"tool_affordance_refs"`
	Capabilities []string `json:"capability_refs"`
	Facts        []string `json:"fact_binding_refs"`
}
type semanticWorkflowPredicate struct {
	Assertions []string `json:"assertions"`
	Objectives []string `json:"objectives"`
	Steps      []struct {
		Step     string   `json:"step"`
		Outcomes []string `json:"outcomes"`
	} `json:"steps"`
}

func (m *semanticModel) executionFacts() error {
	raw := fieldValue(m.transport.ExecutionPolicy)
	if len(raw) > 0 && string(raw) != nullType {
		if err := json.Unmarshal(raw, &m.execution); err != nil {
			return invalid()
		}
	}
	values := fieldValue(m.transport.Workflows)
	for _, name := range m.keys(workflowsSection) {
		row := semanticWorkflow{name: name, start: fieldValue(values[name].Start), steps: map[string]semanticWorkflowStep{}, order: m.keys(workflowsSection, name, "steps")}
		for step, raw := range fieldValue(values[name].Steps) {
			var value semanticWorkflowStep
			if err := json.Unmarshal(raw, &value); err != nil {
				return invalid()
			}
			row.steps[step] = value
		}
		m.workflows = append(m.workflows, row)
	}
	return nil
}
func (m *semanticModel) checkExecution(c *semanticCollector) {
	if m.execution == nil {
		return
	}
	namespaces := map[string]bool{}
	for _, section := range executionSections() {
		for _, name := range m.keys(section) {
			namespaces[lexicalNamespace(name)] = true
		}
	}
	for _, rule := range m.execution.Scopes {
		m.checkExecutionScope(c, rule, namespaces)
	}
	if !m.checkExecutionReferences(c) {
		return
	}
	for _, workflow := range m.workflows {
		m.checkWorkflowPolicies(c, workflow)
	}
}
func (m *semanticModel) checkExecutionScope(c *semanticCollector, rule semanticExecutionScope, namespaces map[string]bool) {
	if _, err := m.scopes.resolve(rule.Scope); err != nil {
		c.report(semanticOwner{}, "Execution policy scope does not resolve to an authored location")
	}
	if !nativeExecutionScope(rule.Scope) {
		c.report(semanticOwner{}, "Execution policy scope has no native execution owner")
	}
	namespace := strings.Join(rule.Namespace, ".")
	if namespace == "" {
		return
	}
	found := false
	for name := range namespaces {
		found = found || namespaceOwns(name, namespace)
	}
	if !found {
		c.report(semanticOwner{}, "Execution policy lexical namespace does not resolve")
	}
	if len(jsonpointer.Tokens(rule.Scope)) >= 2 && !namespaceOwns(m.scopeNamespace(rule.Scope), namespace) {
		c.report(semanticOwner{}, "Execution policy scope escapes its lexical namespace")
	}
}
func (m *semanticModel) scopeNamespace(pointer string) string {
	tokens := jsonpointer.Tokens(pointer)
	if len(tokens) < 2 {
		return ""
	}
	if tokens[0] != forwardingSection {
		return lexicalNamespace(tokens[1])
	}
	for i := range fieldValue(m.transport.ForwardingAgents) {
		canonical, err := m.scopes.resolve("/" + forwardingSection + "/" + strconv.Itoa(i))
		if err == nil && (pointer == canonical || strings.HasPrefix(pointer, canonical+"/")) {
			// Construction checked this same typed ID while indexing forwarders.
			return lexicalNamespace(m.forwarders[i].ID)
		}
	}
	return ""
}
func (m *semanticModel) checkExecutionReferences(c *semanticCollector) bool {
	policies := make([]*semanticExecutionPolicy, 0, len(m.execution.Scopes)+1)
	for i := range m.execution.Scopes {
		policies = append(policies, &m.execution.Scopes[i].Policy)
	}
	if m.execution.Default != nil {
		policies = append(policies, m.execution.Default)
	}
	for _, policy := range policies {
		if policy.Clock != nil && !m.definitions["clocks"][*policy.Clock] {
			c.report(semanticOwner{}, "Execution policy clock reference does not resolve")
		}
		for _, ref := range policy.Evidence {
			if !m.definitions[evidenceRequirementsSection][ref] {
				c.report(semanticOwner{}, "Execution policy evidence reference does not resolve")
				return false
			}
		}
	}
	return true
}
func (m *semanticModel) executionPolicy(scope, namespace string) (*semanticExecutionPolicy, string) {
	var selected *semanticExecutionScope
	for i := range m.execution.Scopes {
		rule := &m.execution.Scopes[i]
		if !namespaceOwns(namespace, strings.Join(rule.Namespace, ".")) || rule.Scope != "" && scope != rule.Scope && !strings.HasPrefix(scope, rule.Scope+"/") {
			continue
		}
		if selected == nil || len(rule.Namespace) > len(selected.Namespace) || len(rule.Namespace) == len(selected.Namespace) && strings.Count(rule.Scope, "/") > strings.Count(selected.Scope, "/") {
			selected = rule
		}
	}
	if selected != nil {
		return &selected.Policy, selected.Scope
	}
	return m.execution.Default, ""
}
func semanticAttempts(number json.Number) *big.Int {
	if number == "" {
		return big.NewInt(1)
	}
	result, _ := new(big.Int).SetString(number.String(), 10)
	return result
}
func workflowAttempts(raw json.RawMessage) *big.Int {
	var number json.Number
	if len(raw) == 0 || json.Unmarshal(raw, &number) != nil {
		return nil
	}
	return semanticAttempts(number)
}
func (m *semanticModel) checkWorkflowPolicies(c *semanticCollector, workflow semanticWorkflow) {
	scope, namespace := "/workflows/"+workflow.name, lexicalNamespace(workflow.name)
	invocation, _ := m.executionPolicy(scope, namespace)
	multiplies := false
	for _, step := range workflow.steps {
		count := workflowAttempts(step.Attempts)
		multiplies = multiplies || step.Type == retryStep && count != nil && count.Cmp(big.NewInt(1)) > 0
	}
	if invocation != nil && semanticAttempts(invocation.Retry.Attempts).Cmp(big.NewInt(1)) > 0 && multiplies {
		c.report(semanticOwner{}, "Execution policy cannot multiply native invocation and workflow retry budgets")
	}
	for _, name := range workflow.order {
		step := workflow.steps[name]
		effective, governingScope := m.executionPolicy(scope+"/steps/"+name, namespace)
		count := workflowAttempts(step.Attempts)
		if effective != nil && strings.Contains(governingScope, "/steps") && step.Type == retryStep && count != nil && semanticAttempts(effective.Retry.Attempts).Cmp(count) != 0 {
			c.report(semanticOwner{}, "Execution policy conflicts with the authored workflow retry bound")
		}
	}
}
