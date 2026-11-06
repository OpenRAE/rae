package contractgen

import (
	"encoding/hex"
	"fmt"
)

func addArchivePieces(output map[string][]byte, archive []byte) {
	const pieceSize = 131072
	for pos, n := 0, 0; pos < len(archive); pos, n = pos+pieceSize, n+1 {
		output[fmt.Sprintf("%s%04d", corpusRoot, n)] = []byte(hex.EncodeToString(archive[pos:min(pos+pieceSize, len(archive))]) + "\n")
	}
}
