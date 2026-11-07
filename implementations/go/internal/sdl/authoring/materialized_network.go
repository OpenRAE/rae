package authoring

import "math/big"

func (c materializedChecks) switchReference(reference string) error {
	if variable(reference) {
		return nil
	}
	if _, present := object(c.value[infrastructureField])[reference]; !present || object(object(c.value[nodesSection])[reference])["type"] != switchType {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) infrastructureEntry(name string, entry map[string]any) error {
	node := object(object(c.value[nodesSection])[name])
	if count, ok := modelInteger(entry["count"]); ok && count.Cmp(big.NewInt(1)) > 0 && (node["type"] == switchType || len(object(node[conditionsSection])) > 0) {
		return semanticInvalid()
	}
	for _, link := range array(entry["links"]) {
		if err := c.switchReference(text(link)); err != nil {
			return err
		}
	}
	if err := c.infrastructureACLs(array(entry["acls"])); err != nil {
		return err
	}
	return c.infrastructureAddresses(entry)
}
func (c materializedChecks) infrastructureACLs(rows []any) error {
	for _, raw := range rows {
		for _, field := range []string{"from_net", "to_net"} {
			if reference := text(object(raw)[field]); reference != "" {
				if err := c.switchReference(reference); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
func (c materializedChecks) infrastructureAddresses(entry map[string]any) error {
	links := map[string]bool{}
	for _, link := range array(entry["links"]) {
		links[text(link)] = true
	}
	for _, row := range array(entry["properties"]) {
		for link, ip := range object(row) {
			if err := c.infrastructureAddress(link, text(ip), links); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c materializedChecks) infrastructureAddress(link, ip string, links map[string]bool) error {
	if variable(link) {
		return nil
	}
	if !links[link] || c.switchReference(link) != nil {
		return semanticInvalid()
	}
	properties := object(object(object(c.value[infrastructureField])[link])["properties"])
	if properties == nil {
		return semanticInvalid()
	}
	return addressInNetwork(ip, text(properties["cidr"]))
}
func addressInNetwork(ip, cidr string) error {
	if variable(ip) || variable(cidr) {
		return nil
	}
	network, err := networkPrefix(cidr)
	if err != nil {
		return semanticInvalid()
	}
	address, err := networkAddress(ip)
	if err != nil || !network.Contains(address.WithZone("")) {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) nodePlatform(node map[string]any) error {
	if node["os_distribution"] != nil && node["os"] == nil || text(node["os_version"]) != "" && node["os_distribution"] == nil {
		return semanticInvalid()
	}
	runtime := object(node["runtime"])
	packages := append([]any(nil), array(runtime["packages"])...)
	for _, raw := range array(runtime["software_components"]) {
		component := object(raw)
		if component["presence"] != "forbidden" && component["package"] != nil {
			packages = append(packages, component["package"])
		}
	}
	for _, raw := range packages {
		architecture := text(object(raw)[architectureField])
		if architecture != "" && !variable(architecture) && !variable(node[architectureField]) && architecture != text(node[architectureField]) {
			return semanticInvalid()
		}
	}
	return nil
}
