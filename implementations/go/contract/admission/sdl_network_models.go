package admission

func sdlNetworkSensor(v any) error {
	return require(sdlSymbolField(v, "network_sensor_id") && fieldsUnique(v, "capture_interfaces", "monitored_network_refs"))
}
func sdlNetworkDetectionEngine(v any) error {
	if !sdlSymbolField(v, "network_detection_engine_id") || !fieldsUnique(v, "app_layer_protocols") {
		return invalid()
	}
	seen := map[string]bool{stringAt(v, "network_detection_engine_id"): true}
	for _, spec := range [][2]string{{"rule_sources", termSourceID}, {"network_sets", "set_id"}, {"output_streams", "stream_id"}, {"control_channels", "channel_id"}} {
		for _, row := range array(at(v, spec[0])) {
			id := stringAt(row, spec[1])
			if seen[id] {
				return invalid()
			}
			seen[id] = true
		}
	}
	return nil
}
func sdlNetworkSet(v any) error {
	return require(sdlSymbolField(v, "set_id") && fieldsUnique(v, "selector_values", "network_refs"))
}
