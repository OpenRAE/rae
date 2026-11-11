package parity

import "strings"

type operationOption struct{ name, value string }

func operationArguments(args []string, allowShort bool) (string, []operationOption, bool) {
	name := ""
	options := []operationOption{}
	literal := false
	for i := 0; i < len(args); i++ {
		arg := args[i]
		if !literal && arg == "--" {
			literal = true
			continue
		}
		if !literal && strings.HasPrefix(arg, "--") {
			option, next, ok := operationOptionAt(args, i)
			if !ok {
				return "", nil, false
			}
			i = next
			options = append(options, option)
			continue
		}
		if !literal && !allowShort && strings.HasPrefix(arg, "-") {
			return "", nil, false
		}
		if name != "" {
			return "", nil, false
		}
		name = arg
	}
	return name, options, name != ""
}

func operationOptionAt(args []string, index int) (operationOption, int, bool) {
	name, value, inline := strings.Cut(args[index], "=")
	if inline {
		return operationOption{name, value}, index, true
	}
	index++
	if index == len(args) {
		return operationOption{}, index, false
	}
	return operationOption{name, args[index]}, index, true
}
