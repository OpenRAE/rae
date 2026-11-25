package analysis

import (
	"cmp"
	"slices"
)

type opacityPoint struct {
	Ordinal     int     `json:"ordinal"`
	Secret      bool    `json:"secret_holds"`
	Reachable   bool    `json:"reachable"`
	Evaluation  bool    `json:"evaluation_point"`
	Initial     string  `json:"initial_information_key"`
	Observation string  `json:"observation_key"`
	Memory      string  `json:"memory_key"`
	Release     string  `json:"release_state_key"`
	Coalition   *string `json:"coalition_fusion_key"`
	Strategy    string  `json:"strategy_ref"`
	Order       string  `json:"order_ref"`
	Scheduler   string  `json:"scheduler_ref"`
	Environment string  `json:"environment_ref"`
	Cut         string  `json:"cut_ref"`
}
type opacityCell struct {
	initial, observation, memory, release, coalition, strategy, order string
	hasCoalition                                                      bool
}

func (p opacityPoint) cell() opacityCell {
	result := opacityCell{initial: p.Initial, observation: p.Observation, memory: p.Memory, release: p.Release, strategy: p.Strategy, order: p.Order}
	if p.Coalition != nil {
		result.coalition = *p.Coalition
		result.hasCoalition = true
	}
	return result
}

type opacityScan struct {
	checked, secret, cellSize int
	counterexample            *int
}

func opacityKernel(points []opacityPoint) opacityScan {
	canonical := slices.Clone(points)
	slices.SortFunc(canonical, func(a, b opacityPoint) int { return cmp.Compare(a.Ordinal, b.Ordinal) })
	type cellCount struct {
		size     int
		hasDecoy bool
	}
	cells := map[opacityCell]cellCount{}
	for _, point := range canonical {
		key := point.cell()
		cell := cells[key]
		cell.size++
		cell.hasDecoy = cell.hasDecoy || !point.Secret
		cells[key] = cell
	}
	result := opacityScan{checked: len(canonical)}
	for _, point := range canonical {
		if !point.Secret {
			continue
		}
		result.secret++
		cell := cells[point.cell()]
		if !cell.hasDecoy && result.counterexample == nil {
			ordinal := point.Ordinal
			result.counterexample = &ordinal
			result.cellSize = cell.size
		}
	}
	return result
}
