package authoring

import (
	"net"
	"net/netip"
	"strings"
)

func networkModel(value map[string]any) error {
	networkVariable, gatewayVariable := variable(value["cidr"]), variable(value["gateway"])
	var network netip.Prefix
	var gateway netip.Addr
	var err error
	if !networkVariable {
		network, err = networkPrefix(text(value["cidr"]))
		if err != nil {
			return err
		}
	}
	if !gatewayVariable {
		gateway, err = networkAddress(text(value["gateway"]))
		if err != nil {
			return err
		}
	}
	if !networkVariable && !gatewayVariable && !network.Contains(gateway.WithZone("")) {
		return invalid()
	}
	return nil
}
func networkAddress(value string) (netip.Addr, error) {
	if strings.ContainsRune(value, '/') || strings.Count(value, "%") > 1 {
		return netip.Addr{}, invalid()
	}
	address, err := netip.ParseAddr(value)
	if err != nil {
		return netip.Addr{}, invalid()
	}
	return address, nil
}
func networkPrefix(value string) (netip.Prefix, error) {
	host, bits, hasPrefix := strings.Cut(value, "/")
	address, err := networkAddress(host)
	if err != nil {
		return netip.Prefix{}, err
	}
	address = address.WithZone("")
	if !hasPrefix {
		return netip.PrefixFrom(address, address.BitLen()), nil
	}
	if prefix, parseErr := netip.ParsePrefix(address.String() + "/" + bits); parseErr == nil {
		return prefix, nil
	}
	if !address.Is4() {
		return netip.Prefix{}, invalid()
	}
	mask, err := netip.ParseAddr(bits)
	if err != nil || !mask.Is4() {
		return netip.Prefix{}, invalid()
	}
	length, err := networkMask(mask.As4())
	if err != nil {
		return netip.Prefix{}, err
	}
	return netip.PrefixFrom(address, length), nil
}
func networkMask(mask [4]byte) (int, error) {
	ones, width := net.IPMask(mask[:]).Size()
	if width != 0 {
		return ones, nil
	}
	for i := range mask {
		mask[i] = ^mask[i]
	}
	ones, width = net.IPMask(mask[:]).Size()
	if width == 0 {
		return 0, invalid()
	}
	return ones, nil
}
