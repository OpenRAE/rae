package softwareversion

import "testing"

func FuzzVersionOrdering(f *testing.F) {
	for _, pair := range [][2]string{{"1.0", "1.0-0"}, {"1.0~", "1.0"}, {"2.0^20250611", "2.0.1"}, {"9223372036854775808:1", "9223372036854775809:0"}, {"1.0.0", "2.0.0"}} {
		f.Add(pair[0], pair[1])
	}
	f.Fuzz(func(t *testing.T, left, right string) {
		if len(left) > 256 || len(right) > 256 {
			t.Skip()
		}
		for _, relation := range []string{"numeric-triplet", "debian", "rpm"} {
			grammar := pattern(relation)
			if !grammar.MatchString(left) || !grammar.MatchString(right) {
				continue
			}
			forward, backward := compare(relation, left, right), compare(relation, right, left)
			if compare(relation, left, left) != 0 || forward < 0 != (backward > 0) || forward == 0 != (backward == 0) {
				t.Errorf("%s order is not reflexive and antisymmetric for %q, %q", relation, left, right)
			}
		}
	})
}
