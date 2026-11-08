package authoring

func workflowClosure(edges map[string][]string, roots []string, stop string) map[string]bool {
	seen := map[string]bool{}
	pending := append([]string(nil), roots...)
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if node == stop || seen[node] {
			continue
		}
		seen[node] = true
		pending = append(pending, edges[node]...)
	}
	return seen
}
