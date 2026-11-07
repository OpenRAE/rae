package parity

import (
	"bytes"
	"os"
	"slices"
	"sync"
)

var sharedTestCases = sync.OnceValues(func() ([]Case, error) { //nolint:gochecknoglobals // Immutable checked-in corpus; each test receives independent mutable carriers below.
	return Load(os.DirFS("testdata"))
})

func loadTestCases() ([]Case, error) {
	cases, err := sharedTestCases()
	if err != nil {
		return nil, err
	}
	result := make([]Case, len(cases))
	for i, c := range cases {
		c.Args = slices.Clone(c.Args)
		c.Result = bytes.Clone(c.Result)
		if c.Files != nil {
			files := make(map[string][]byte, len(c.Files))
			for name, content := range c.Files {
				files[name] = bytes.Clone(content)
			}
			c.Files = files
		}
		result[i] = c
	}
	return result, nil
}
