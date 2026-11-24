package parity

import "testing"

func TestOperationArgumentBoundariesPreserveLiteralFilenames(t *testing.T) {
	for _, args := range [][]string{nil, {"one", "two"}, {"--output"}, {"-x"}} {
		if _, _, ok := operationArguments(args, false); ok {
			t.Fatalf("invalid arguments accepted: %v", args)
		}
	}
	name, options, ok := operationArguments([]string{"--output=json", "--lock", "pinned", "--", "-source.sdl"}, false)
	if !ok || name != "-source.sdl" || len(options) != 2 || options[0].value != "json" || options[1].value != "pinned" {
		t.Fatalf("literal filename or explicit options lost: %q %+v %t", name, options, ok)
	}
	if name, _, ok := operationArguments([]string{"-"}, true); !ok || name != "-" {
		t.Fatal("explicit short source was not retained")
	}
}

func TestSemanticCommandOptionsRefuseInvalidPolicyAndTransform(t *testing.T) {
	for _, args := range [][]string{nil, {"other", "resolve", "file"}, {"semantic", "future", "file"}, {"semantic", "resolve", "one", "two"}, {"semantic", "resolve", "file", "--unknown=x"}, {"semantic", "resolve", "file", "--migration-policy=future"}, {"semantic", "resolve", "file", "--output=yaml"}, {"semantic", "resolve", "file", "--transform=canonical"}, {"semantic", "transform", "file", "--transform=future"}} {
		if _, ok := semanticArguments(args); ok {
			t.Fatalf("invalid semantic command accepted: %v", args)
		}
	}
	command, ok := semanticArguments([]string{"semantic", "transform", "file", "--contract=sdl-yaml/v1", "--migration-policy=accept", "--output=json", "--transform=format"})
	if !ok || command.name != "file" || command.policy != "accept" || command.transform != "format" {
		t.Fatalf("valid semantic options changed: %+v", command)
	}
}

func TestModuleCommandOptionsStayWithinTheirOperation(t *testing.T) {
	for _, args := range [][]string{nil, {"other", "resolve", "file"}, {"sdl", "future", "file"}, {"sdl", "resolve", "file", "--private-key=key"}, {"sdl", "verify-imports", "file", "--lockfile=lock"}, {"sdl", "resolve", "one", "two"}} {
		if _, ok := moduleArguments(args); ok {
			t.Fatalf("invalid module options accepted: %v", args)
		}
	}
	command, ok := moduleArguments([]string{"sdl", "publish", "file", "--output-dir=out", "--signer-id=signer", "--private-key=key"})
	if !ok || command.name != "file" || command.output != "out" || command.signer != "signer" || command.key != "key" {
		t.Fatalf("valid publication options changed: %+v", command)
	}
}
