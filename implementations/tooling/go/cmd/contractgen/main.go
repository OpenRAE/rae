// Command contractgen generates or checks the Go contract bindings and corpus.
// Run it from the repository root after building it from the tooling module.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"

	"github.com/OpenRAE/rae/implementations/tooling/go/contractgen"
)

func main() { os.Exit(run(os.Args[1:], os.Stderr)) }

func run(args []string, stderr io.Writer) int {
	flags := flag.NewFlagSet("contractgen", flag.ContinueOnError)
	flags.SetOutput(stderr)
	check := flags.Bool("check", false, "compare the complete generated output")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if flags.NArg() != 0 {
		_, _ = fmt.Fprintln(stderr, "usage: contractgen [-check]")
		return 2
	}
	if err := generate(*check); err != nil {
		_, _ = fmt.Fprintln(stderr, err)
		return 1
	}
	return 0
}

func generate(check bool) error {
	output, err := contractgen.Generate(os.DirFS("."))
	if err != nil {
		return err
	}
	if check {
		return contractgen.Check(os.DirFS("."), output)
	}
	for name, data := range output {
		if err := os.MkdirAll(filepath.Dir(name), 0750); err != nil {
			return err
		}
		if err := os.WriteFile(name, data, 0600); err != nil {
			return err
		}
	}
	return nil
}
