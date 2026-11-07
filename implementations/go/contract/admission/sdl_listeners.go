package admission

import (
	"net/netip"
	"regexp"
	"strings"
)

var (
	sdlHostnameLabel = regexp.MustCompile(`^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\z`)
	sdlInterfaceName = regexp.MustCompile(`^[A-Za-z0-9_.:@-]+\z`)
)

const (
	termTCP           = "tcp"
	termUnix          = "unix"
	termIPv4          = "ipv4"
	termIPv6          = "ipv6"
	termLocalSocket   = "local_socket"
	termLoopbackOnly  = "loopback_only"
	termNetworkFacing = "network_facing"
	termWildcard      = "wildcard"
	termNodeLocal     = "node_local"
)

func sdlOptionalPort(v any) bool {
	if v == nil || variableRef(text(v)) {
		return true
	}
	n, ok := integer(v)
	return ok && n >= 1 && n <= 65535
}
func sdlListenerAddress(value string) bool {
	if value == "" || variableRef(value) {
		return true
	}
	if strings.IndexFunc(value, sdlWhitespace) >= 0 {
		return false
	}
	if value == "*" || sdlIPAddress(value) {
		return true
	}
	for label := range strings.SplitSeq(value, ".") {
		if !sdlHostnameLabel.MatchString(label) {
			return false
		}
	}
	return true
}

type sdlListenerInput struct {
	value                                    any
	protocol, address, family, scope, socket string
	network                                  bool
}

func sdlListenerModel(v any) error {
	input := sdlListenerInput{value: v, protocol: stringAt(v, "protocol"), address: stringAt(v, "address"), family: text(defaultMember(v, "address_family", "unspecified")), scope: text(defaultMember(v, "scope", statusUnknown)), socket: stringAt(v, "socket_path")}
	if input.protocol == termTCP {
		input.protocol = ""
	}
	bind := stringAt(v, "bind_interface")
	input.network = at(v, "port") != nil || input.address != "" || bind != ""
	if !sdlOptionalPort(at(v, "port")) || !sdlListenerAddress(input.address) || input.socket != "" && !variableRef(input.socket) && !strings.HasPrefix(input.socket, "/") && !strings.HasPrefix(input.socket, "@") || bind != "" && !variableRef(bind) && !sdlInterfaceName.MatchString(bind) {
		return invalid()
	}
	for _, check := range []func() error{input.transport, input.familyShape, input.scopeShape, input.familyScope, input.publishedRefs} {
		if err := check(); err != nil {
			return err
		}
	}
	return nil
}
func sdlNetworkProtocol(value string) bool {
	return value == termTCP || value == "udp" || value == "sctp"
}
func (v sdlListenerInput) transport() error {
	if v.protocol == termUnix {
		return require(!v.network)
	}
	if sdlNetworkProtocol(v.protocol) {
		return require(v.socket == "")
	}
	return require(v.socket == "" || !v.network)
}
func (v sdlListenerInput) familyShape() error {
	if v.family != termUnix && v.family != termIPv4 && v.family != termIPv6 {
		return nil
	}
	if (v.protocol == termUnix || v.socket != "") && v.family != termUnix || (sdlNetworkProtocol(v.protocol) || v.network) && v.family == termUnix {
		return invalid()
	}
	address, parsed := sdlListenerIP(v.address)
	if !parsed {
		return nil
	}
	expected := termIPv6
	if address.Is4() {
		expected = termIPv4
	}
	return require(v.family == expected)
}
func sdlListenerIP(value string) (netip.Addr, bool) {
	address, err := netip.ParseAddr(value)
	return address, err == nil && !variableRef(value) && value != "*"
}
func (v sdlListenerInput) scopeShape() error {
	switch v.scope {
	case termWildcard, termLoopbackOnly, termNetworkFacing, termNodeLocal, termLocalSocket:
	default:
		return nil
	}
	if (sdlNetworkProtocol(v.protocol) || v.network) && v.scope == termLocalSocket || (v.socket != "" || v.protocol == termUnix) && v.scope != termLocalSocket {
		return invalid()
	}
	address, parsed := sdlListenerIP(v.address)
	wildcard, loopback, otherIP := v.address == "*", v.address == "localhost", false
	if parsed {
		wildcard = address.Unmap().IsUnspecified()
		loopback = address.Unmap().IsLoopback()
		otherIP = !loopback
	}
	return require((!wildcard || v.scope == termWildcard) && (!loopback || v.scope != termNetworkFacing) && (!otherIP || v.scope != termLoopbackOnly))
}
func (v sdlListenerInput) familyScope() error {
	if variableRef(v.family) || variableRef(v.scope) {
		return nil
	}
	if v.family == termUnix {
		return require(v.scope != termWildcard && v.scope != termLoopbackOnly && v.scope != termNetworkFacing && v.scope != termNodeLocal)
	}
	return require(v.family != termIPv4 && v.family != termIPv6 || v.scope != termLocalSocket)
}
func (v sdlListenerInput) publishedRefs() error {
	seen := map[[4]string]bool{}
	for _, ref := range array(at(v.value, "published_port_refs")) {
		key := [4]string{stringAt(ref, "host_ip"), sdlScalarIdentity(at(ref, "host_port")), sdlScalarIdentity(at(ref, "container_port")), text(defaultMember(ref, "protocol", termTCP))}
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
