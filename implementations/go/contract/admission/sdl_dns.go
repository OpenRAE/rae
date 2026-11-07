package admission

import (
	"net/netip"
	"slices"
	"strings"
)

func sdlDNSName(value string) bool {
	return variableRef(value) || value != "" && strings.IndexFunc(value, sdlWhitespace) < 0
}
func sdlDNSNames(v any, fields ...string) bool {
	for _, field := range fields {
		if !sdlDNSName(stringAt(v, field)) {
			return false
		}
	}
	return true
}

func sdlDNSRecord(v any) error {
	if target := stringAt(v, "target"); target != "" && !sdlDNSName(target) {
		return invalid()
	}
	if slices.Contains(stringsOf(at(v, "text")), "") {
		return invalid()
	}
	for _, field := range []string{"rdata", fieldAddress, "target"} {
		if stringAt(v, field) != "" {
			return nil
		}
	}
	return require(len(array(at(v, "text"))) > 0 || at(v, "soa") != nil || at(v, "mx") != nil || at(v, "srv") != nil)
}
func sdlDNSZone(v any) error {
	if !sdlSymbolField(v, "zone_id") || !sdlDNSName(stringAt(v, termName)) || !sdlAbsoluteList(v, "zone_file_refs") {
		return invalid()
	}
	if !sdlUniqueKey(at(v, "rrsets"), "rrset_id", false) {
		return invalid()
	}
	seen := map[[3]string]bool{}
	for _, rrset := range array(at(v, "rrsets")) {
		key := [3]string{sdlProtocol(stringAt(rrset, "owner")), sdlProtocol(text(defaultMember(rrset, "zone_class", "in"))), sdlProtocol(stringAt(rrset, "record_type"))}
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
func sdlDNSRRSet(v any) error {
	if !sdlSymbolField(v, "rrset_id") || !sdlDNSName(stringAt(v, "owner")) {
		return invalid()
	}
	rows := array(at(v, "records"))
	kind := stringAt(v, "record_type")
	if len(rows) == 0 {
		return invalid()
	}
	if !variableRef(kind) && ((kind == termOther) != (at(v, "type_code") != nil)) {
		return invalid()
	}
	for _, row := range rows {
		if err := sdlDNSPayload(kind, row); err != nil {
			return err
		}
	}
	return nil
}
func sdlDNSService(v any) error {
	if !sdlSymbolField(v, "dns_service_id") || !sdlAbsoluteList(v, "configuration_file_refs", "log_file_refs") {
		return invalid()
	}
	return sdlUniqueCollections([2]string{"zones", "zone_id"}, [2]string{termSettings, termName})(v)
}
func sdlDNSPayload(kind string, v any) error {
	address := stringAt(v, fieldAddress)
	if variableRef(kind) {
		return require(sdlIPAddress(address))
	}
	if address != "" {
		if err := sdlDNSAddress(kind, address); err != nil {
			return err
		}
	}
	if stringAt(v, "target") != "" && !slices.Contains([]string{"cname", "ns", "ptr"}, kind) {
		return invalid()
	}
	for _, field := range []string{"soa", "mx", "srv"} {
		if at(v, field) != nil && kind != field {
			return invalid()
		}
	}
	return require(len(array(at(v, "text"))) == 0 || kind == "txt")
}
func sdlDNSAddress(kind, value string) error {
	if kind != "a" && kind != "aaaa" {
		return invalid()
	}
	if variableRef(value) {
		return nil
	}
	address, err := netip.ParseAddr(value)
	return require(err == nil && (kind == "a") == address.Is4())
}
