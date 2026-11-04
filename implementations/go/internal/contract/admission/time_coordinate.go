package admission

import "maps"

// Python model comparisons include defaults, while admitted evidence stays exact.
// Only schema-owned coordinates enter this view; payload maps are never walked.
func coordinateView(value any) map[string]any {
	source := object(value)
	if source == nil {
		return nil
	}
	if _, present := source["tick"]; !present {
		return nil
	}
	view := maps.Clone(source)
	for _, field := range []string{"segment", termMicrostep} {
		if _, present := view[field]; !present {
			view[field] = jsonZero
		}
	}
	return view
}

func coordinateEqual(left, right any) bool {
	a, b := coordinateView(left), coordinateView(right)
	return a != nil && b != nil && equal(a, b)
}
