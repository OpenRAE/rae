package admission

import "math/big"

func (r *materializationExecution) nodeBindings() error {
	rows := array(at(r.current.full, "materialization_provenance", "resource_bindings"))
	nodes, instances := map[string]bool{}, map[string]map[string]bool{}
	for _, row := range rows {
		if err := r.nodeBinding(row, nodes, instances); err != nil {
			return err
		}
	}
	if !equalSet(nodes, keySet(at(r.current.full, termNodes))) {
		return invalid()
	}
	for address, indices := range instances {
		if err := materializationIndices(r.current.resources[address], indices, len(rows)); err != nil {
			return err
		}
	}
	return nil
}

func materializationIndices(resource any, indices map[string]bool, bound int) error {
	raw := at(resource, "payload", "count")
	if raw == nil {
		raw = jsonOne
	}
	count, ok := number(raw)
	if !ok {
		return invalid()
	}
	if count.Sign() == 0 {
		count = big.NewRat(1, 1)
	}
	if !count.IsInt() || count.Sign() < 0 || !count.Num().IsInt64() || count.Num().Int64() > int64(bound) {
		return invalid()
	}
	total := count.Num().Int64()
	if total == 1 && len(indices) == 1 && indices[termNull] {
		return nil
	}
	if int64(len(indices)) != total {
		return invalid()
	}
	// Cardinality and bounded integer membership imply the exact interval without
	// constructing a range from a potentially enormous untrusted replica count.
	for index := range indices {
		n, valid := new(big.Int).SetString(index, 10)
		if !valid || n.Sign() < 0 || n.Cmp(count.Num()) >= 0 {
			return invalid()
		}
	}
	return nil
}

func (r *materializationExecution) nodeBinding(row any, nodes map[string]bool, instances map[string]map[string]bool) error {
	name, address := stringAt(row, "node_name"), stringAt(row, "address")
	resource := r.current.resources[address]
	if resource == nil || stringAt(resource, "payload", termName) != name {
		return invalid()
	}
	_, original := object(at(r.original.full, termNodes))[name]
	if original && stringAt(row, "source_node") != name || !original && at(row, "source_node") != nil {
		return invalid()
	}
	nodes[name] = true
	index, err := materializationInstanceIndex(at(row, "instance_index"))
	if err != nil {
		return err
	}
	if instances[address] == nil {
		instances[address] = map[string]bool{}
	}
	if instances[address][index] {
		return invalid()
	}
	instances[address][index] = true
	return nil
}
