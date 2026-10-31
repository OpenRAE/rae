package randstream

import (
	"encoding/hex"
	"errors"
	"math"
	"testing"
)

// The values come from the published vector
// contracts/fixtures/random-stream-vectors/blake3-xof-v1/zero-heavy-seed-and-address.json.
const (
	zeroSeed    = "0000000000000000000000000000000000000000000000000000000000000000"
	zeroKey     = "39a7b17cae76d0fc6cb1570061a75120f2b674895df48587c4d82853906866fd"
	zeroAddress = `{"draw_purpose":"other","local_coordinate":0,"namespace":"n","selection_policy_id":"p","trial_coordinate":{},"variation_point_id":"v"}`
	zeroBlock   = "603c8a2cc1ba9d29bd28d13e4fe8e0cf315b326ea231d26537c6348e22e23d94"
)

func zeroHeavyKey(t *testing.T) Key {
	t.Helper()
	seed, err := PublicSeed("hex-fixed-width", zeroSeed)
	if err != nil {
		t.Fatalf("PublicSeed() error = %v", err)
	}
	key, err := DeriveKey("blake3-xof-v1", seed)
	if err != nil {
		t.Fatalf("DeriveKey() error = %v", err)
	}
	return key
}

func TestKeyAndBlockMatchThePublishedVector(t *testing.T) {
	key := zeroHeavyKey(t)
	if got := hex.EncodeToString(key[:]); got != zeroKey {
		t.Errorf("DeriveKey() = %s, want %s", got, zeroKey)
	}
	block, err := Block(key, []byte(zeroAddress), 0, 0, BlockBytes)
	if err != nil {
		t.Fatalf("Block() error = %v", err)
	}
	if got := hex.EncodeToString(block); got != zeroBlock {
		t.Errorf("Block() = %s, want %s", got, zeroBlock)
	}
	tail, err := Block(key, []byte(zeroAddress), 0, 16, 16)
	if err != nil || hex.EncodeToString(tail) != zeroBlock[32:] {
		t.Errorf("Block(offset 16) = %x, %v, want the second half of the block", tail, err)
	}
}

// The published vector bounded-integer-basic-draw reads its block at local
// coordinate 5. A block at 64 output bytes or more needs a correct seek in the
// extendable output; lukechampine.com/blake3 v1.4.1 returns other bytes there.
func TestBlockAtALaterCoordinateMatchesTheReference(t *testing.T) {
	const (
		seed    = "a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5"
		address = `{"draw_purpose":"sampling-selection","local_coordinate":5,"namespace":"study-namespace",` +
			`"selection_policy_id":"policy-b","trial_coordinate":{"condition_id":"condition-b"},"variation_point_id":"point-b"}`
		want = "e5a8a68e2efe0edfc587c1e4c43a795672e9c22961ec698f50cc1250a6b4b565"
	)
	entropy, err := PublicSeed("hex-fixed-width", seed)
	if err != nil {
		t.Fatalf("PublicSeed() error = %v", err)
	}
	key, err := DeriveKey("blake3-xof-v1", entropy)
	if err != nil {
		t.Fatalf("DeriveKey() error = %v", err)
	}
	block, err := Block(key, []byte(address), 5, 0, BlockBytes)
	if err != nil || hex.EncodeToString(block) != want {
		t.Errorf("Block(coordinate 5) = %x, %v, want %s", block, err, want)
	}
}

func TestBoundedIntDrawsWithinTheRangeAndRecordsExhaustion(t *testing.T) {
	key := zeroHeavyKey(t)
	single, err := BoundedInt(key, []byte(zeroAddress), 0, 7, 7, 1)
	if err != nil || single != (Draw{Value: 7}) {
		t.Errorf("BoundedInt(7, 7) = %+v, %v, want 7 without rejections", single, err)
	}
	wide, err := BoundedInt(key, []byte(zeroAddress), 3, math.MinInt64, math.MaxInt64, 4)
	if err != nil || wide.Exhausted {
		t.Errorf("BoundedInt(full range) = %+v, %v, want a value", wide, err)
	}
	// A width of 129 accepts candidates below 129 only: about half of them.
	var exhausted bool
	for coordinate := range int64(64) {
		draw, err := BoundedInt(key, []byte(zeroAddress), coordinate, 0, 128, 1)
		if err != nil {
			t.Fatalf("BoundedInt() error = %v", err)
		}
		if draw.Exhausted {
			exhausted = draw.Attempts == 1
			break
		}
	}
	if !exhausted {
		t.Error("BoundedInt(0, 128, one attempt) never exhausted in 64 coordinates")
	}
}

func TestFunctionsRefuseInvalidInput(t *testing.T) {
	key := zeroHeavyKey(t)
	for name, err := range map[string]error{
		"seed encoding":     func() error { _, err := PublicSeed("base64", zeroSeed); return err }(),
		"seed length":       func() error { _, err := PublicSeed("hex-fixed-width", "00"); return err }(),
		"seed digits":       func() error { _, err := PublicSeed("hex-fixed-width", "zz"+zeroSeed[2:]); return err }(),
		"profile":           func() error { _, err := DeriveKey("blake3-xof-v2", make([]byte, KeyBytes)); return err }(),
		"entropy length":    func() error { _, err := DeriveKey("blake3-xof-participant-v1", make([]byte, 16)); return err }(),
		"block length":      func() error { _, err := Block(key, nil, 0, 0, 0); return err }(),
		"coordinate":        func() error { _, err := Block(key, nil, math.MaxInt64/BlockBytes+1, 0, 1); return err }(),
		"offset":            func() error { _, err := Block(key, nil, 0, -1, 1); return err }(),
		"negative position": func() error { _, err := Block(key, nil, -1, 0, 1); return err }(),
		"reversed range":    func() error { _, err := BoundedInt(key, nil, 0, 2, 1, 1); return err }(),
		"no attempts":       func() error { _, err := BoundedInt(key, nil, 0, 0, 1, 0); return err }(),
		"draw out of range": func() error { _, err := BoundedInt(key, nil, math.MaxInt64/BlockBytes+1, 0, 1, 2); return err }(),
	} {
		if !errors.Is(err, ErrInput) {
			t.Errorf("%s: error = %v, want ErrInput", name, err)
		}
	}
}

func FuzzBoundedIntStaysInItsRange(f *testing.F) {
	f.Add([]byte(zeroAddress), int64(0), int64(0), int64(199))
	f.Add([]byte("{}"), int64(9), int64(-5), int64(5))
	key := Key{1, 2, 3}
	f.Fuzz(func(t *testing.T, address []byte, coordinate, minimum, maximum int64) {
		if maximum < minimum || coordinate < 0 || coordinate > math.MaxInt64/BlockBytes-1 {
			t.Skip()
		}
		draw, err := BoundedInt(key, address, coordinate, minimum, maximum, 8)
		if err != nil {
			t.Fatalf("BoundedInt() error = %v", err)
		}
		if !draw.Exhausted && (draw.Value < minimum || draw.Value > maximum) {
			t.Errorf("BoundedInt(%d, %d) = %d, want a value in the range", minimum, maximum, draw.Value)
		}
		again, _ := BoundedInt(key, address, coordinate, minimum, maximum, 8)
		if again != draw {
			t.Errorf("BoundedInt() = %+v, then %+v, want the same draw", draw, again)
		}
	})
}
