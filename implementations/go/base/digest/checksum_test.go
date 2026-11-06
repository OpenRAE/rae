package digest

import (
	"encoding/hex"
	"testing"
)

func TestChecksumIncrementalPublishedAlgorithms(t *testing.T) {
	for algorithm, want := range map[string]string{
		"sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
		"sha384": "cb00753f45a35e8bb5a03d699ac65007272c32ab0eded1631a8b605a43ff5bed8086072ba1e7cc2358baeca134c825a7",
		"sha512": "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f",
		"blake3": "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85",
	} {
		h, ok := NewChecksum(algorithm)
		if !ok {
			t.Fatal("missing published algorithm")
		}
		for _, part := range []string{"a", "b", "c"} {
			if _, err := h.Write([]byte(part)); err != nil {
				t.Fatal(err)
			}
		}
		if got := hex.EncodeToString(h.Sum(nil)); got != want {
			t.Errorf("%s checksum=%s, want %s", algorithm, got, want)
		}
	}
	for _, algorithm := range []string{"", "SHA256", "md5", "blake3-xof"} {
		if h, ok := NewChecksum(algorithm); h != nil || ok {
			t.Fatal("accepted unknown checksum algorithm")
		}
	}
}
