package authoring

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

func executionSection(section string) bool {
	return slices.Contains(executionSections(), section)
}

func nativeExecutionScope(pointer string) bool {
	tokens := jsonpointer.Tokens(pointer)
	if len(tokens) == 0 {
		return true
	}
	if !executionSection(tokens[0]) {
		return false
	}
	if len(tokens) <= 2 {
		return true
	}
	nested := tokens[0] == workflowsSection && tokens[2] == "steps" || tokens[0] == nodesSection && (tokens[2] == featuresSection || tokens[2] == conditionsSection || tokens[2] == injectsSection)
	return nested && len(tokens) <= 4
}

func lexicalNamespace(name string) string {
	if namespace, _, found := strings.CutLast(name, "."); found {
		return namespace
	}
	return ""
}

func namespaceOwns(owner, prefix string) bool {
	return prefix == "" || owner == prefix || strings.HasPrefix(owner, prefix+".")
}
