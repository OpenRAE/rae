package admission

import (
	"regexp"
	"strings"
)

var sdlDomainLabel = regexp.MustCompile(`^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\z`)

func sdlIdentityDomain(v any) error {
	dns := stringAt(v, "dns_name")
	if dns != "" && !variableRef(dns) {
		if len(dns) > 253 {
			return invalid()
		}
		for label := range strings.SplitSeq(dns, ".") {
			if !sdlDomainLabel.MatchString(label) {
				return invalid()
			}
		}
	}
	netbios := stringAt(v, "netbios_name")
	return require(netbios == "" || variableRef(netbios) || len(netbios) <= 15 && sdlDomainLabel.MatchString(netbios))
}
