package admission

import (
	"math/big"
	"net/netip"
	"regexp"
	"strings"
)

var sdlSymbol = regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,63}\z`)
var sdlMAC = regexp.MustCompile(`^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}\z`)
var sdlMailAddress = regexp.MustCompile(`^[^@\s]+@[^@\s]+$`)
var sdlPermissionMode = regexp.MustCompile(`^(0o)?[0-7]{3,4}$`)

func sdlDatabaseListenAddress(value string) bool {
	return sdlDNSName(value) && (strings.HasPrefix(value, "/") || sdlListenerAddress(value))
}

func sdlFilesystemMode(value any) bool {
	if value == nil || value == "" || variableRef(text(value)) {
		return true
	}
	if mode, ok := value.(string); ok {
		return sdlPermissionMode.MatchString(strings.TrimFunc(mode, sdlWhitespace))
	}
	n, valid := number(value)
	return valid && n.IsInt() && n.Sign() >= 0 && n.Cmp(big.NewRat(4095, 1)) <= 0
}

func sdlSymbolField(v any, field string) bool { return sdlSymbol.MatchString(stringAt(v, field)) }
func sdlAbsoluteFields(v any, optional bool, fields ...string) bool {
	for _, field := range fields {
		if !absoluteSDLPath(stringAt(v, field), optional) {
			return false
		}
	}
	return true
}
func sdlAbsoluteList(v any, fields ...string) bool {
	for _, field := range fields {
		for _, value := range stringsOf(at(v, field)) {
			if !absoluteSDLPath(value, false) {
				return false
			}
		}
	}
	return true
}
func sdlURLPath(value string, optional bool) bool {
	if variableRef(value) || optional && value == "" {
		return true
	}
	return strings.HasPrefix(value, "/") && strings.IndexFunc(value, sdlWhitespace) < 0
}
func sdlLocalUser(v any) error {
	return require(nonblankSDLFields(v, "username") && sdlAbsoluteFields(v, true, "home", "shell"))
}
func sdlIPAddress(value string) bool {
	if value == "" || variableRef(value) {
		return true
	}
	_, err := netip.ParseAddr(value)
	return err == nil && strings.Count(value, "%") <= 1
}
func sdlNetworkEndpoint(v any) error {
	mac := stringAt(v, "mac_address")
	return require(nonblankSDLFields(v, "network") && fieldsUnique(v, "aliases", "dns_names") && sdlIPAddress(stringAt(v, "ip_address")) && sdlIPAddress(stringAt(v, "gateway")) && (mac == "" || variableRef(mac) || sdlMAC.MatchString(mac)))
}
func sdlPublishedPort(v any) error {
	return require(at(v, "container_port") != nil && sdlOptionalPort(at(v, "container_port")) && sdlOptionalPort(at(v, "host_port")) && !sdlBlank(text(defaultMember(v, "protocol", termTCP))) && sdlIPAddress(stringAt(v, "host_ip")))
}
