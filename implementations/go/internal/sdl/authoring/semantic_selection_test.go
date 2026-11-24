package authoring

import (
	"encoding/json"
	"os"
	"testing"
)

type selectionVector struct {
	Name      string      `json:"name"`
	Variables [][2]string `json:"variables"`
	Groups    []struct {
		Members []int `json:"members"`
		Minimum int   `json:"minimum"`
		Maximum int   `json:"maximum"`
	} `json:"groups"`
	Clauses  [][2][2]json.RawMessage `json:"clauses"`
	Budget   int                     `json:"budget"`
	Required []int                   `json:"required"`
	Calls    []struct {
		Witness   bool `json:"witness"`
		Exhausted bool `json:"exhausted"`
		Remaining int  `json:"remaining"`
	} `json:"calls"`
}

func TestSemanticSelectionReferenceBudgetAndWitnesses(t *testing.T) {
	data, err := os.ReadFile("testdata/selection.json")
	if err != nil {
		t.Fatal(err)
	}
	var vectors []selectionVector
	if json.Unmarshal(data, &vectors) != nil {
		t.Fatal("invalid reference selection vectors")
	}
	if selectionStateLimit != 100000 {
		t.Fatal("selection state limit differs from the reference")
	}
	for _, vector := range vectors {
		t.Run(vector.Name, func(t *testing.T) { checkSelectionVector(t, vector) })
	}
}
func checkSelectionVector(t *testing.T, vector selectionVector) {
	t.Helper()
	solver := semanticSelectionSolver{remaining: vector.Budget}
	for _, variable := range vector.Variables {
		solver.variables = append(solver.variables, semanticSelectionVariable{variable[0], variable[1]})
	}
	for _, group := range vector.Groups {
		solver.groups = append(solver.groups, semanticSelectionGroup{group.Members, group.Minimum, group.Maximum})
	}
	for _, clause := range vector.Clauses {
		solver.clauses = append(solver.clauses, [2]semanticSelectionLiteral{selectionTestLiteral(t, clause[0]), selectionTestLiteral(t, clause[1])})
	}
	solver.orderBranches()
	if len(vector.Calls) != len(vector.Required) {
		t.Fatal("reference witness count differs")
	}
	for i, required := range vector.Required {
		valid, exhausted := solver.witness(required)
		expected := vector.Calls[i]
		if valid != expected.Witness || exhausted != expected.Exhausted || solver.remaining != expected.Remaining {
			t.Fatalf("call %d = (%t,%t,%d); want (%t,%t,%d)", i, valid, exhausted, solver.remaining, expected.Witness, expected.Exhausted, expected.Remaining)
		}
	}
}
func selectionTestLiteral(t *testing.T, raw [2]json.RawMessage) semanticSelectionLiteral {
	t.Helper()
	var variable int
	var value bool
	if json.Unmarshal(raw[0], &variable) != nil || json.Unmarshal(raw[1], &value) != nil {
		t.Fatal("invalid reference literal")
	}
	literal := semanticSelectionLiteral{variable: variable, value: selectionFalse}
	if value {
		literal.value = selectionTrue
	}
	return literal
}
