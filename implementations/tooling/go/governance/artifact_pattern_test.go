package governance

import "testing"

func TestArtifactPathPatternReference(t *testing.T) {
	fixture := readReference[struct {
		Pattern string
		Cases   []struct {
			Value   string
			Matches bool
		}
	}](t, "lock-pattern-reference")
	if fixture.Pattern != toolingManifestPattern {
		t.Fatal("fixed path-profile adapter no longer names the reference pattern")
	}
	pattern, err := compileToolingPattern(fixture.Pattern)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range fixture.Cases {
		if got := pattern.MatchString(tc.Value); got != tc.Matches {
			t.Errorf("%q matches=%t want=%t", tc.Value, got, tc.Matches)
		}
	}
}

func TestSourceSnapshotSelectionsRepository(t *testing.T) {
	r, err := openRepository("../../../..")
	if err != nil {
		t.Fatal(err)
	}
	defer func() { _ = r.root.Close() }()
	for _, tc := range []struct{ id, version string }{
		{"attack-enterprise-tactics-snapshot", "v19.1"},
		{"atlas-tactics-snapshot", "2026.06"},
		{"nist-csf-defensive-categories-snapshot", "2.0"},
		{"w3c-activitystreams-activity-types-snapshot", "REC-activitystreams-vocabulary-20170523"},
		{"fipa-communicative-acts-snapshot", "SC00037J-2002-12-03"},
	} {
		t.Run(tc.id, func(t *testing.T) {
			value, err := selectSourceSnapshot(r, tc.id, tc.version)
			if err != nil || value.url == "" {
				t.Fatalf("selection=%+v error=%v", value, err)
			}
		})
	}
}
