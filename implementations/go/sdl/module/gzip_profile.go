package module

import (
	"encoding/binary"
	"hash/crc32"
	"math"

	compatible "github.com/autonubil/go-wazuh/pkg/zlib"
)

// publisherGzip retains the established mtime=0, level=9, no-filename envelope
// and zlib's raw deflate profile. Received data uses the standard decoder.
func publisherGzip(raw []byte, limit int64) ([]byte, error) {
	size := uint64(len(raw))
	if size > math.MaxUint32 {
		return nil, invalid()
	}
	compressed, err := compatible.CompressWith(raw, 9, -15, 8, compatible.StrategyDefault)
	if err != nil {
		return nil, operational(err)
	}
	if int64(len(compressed))+18 > limit {
		return nil, invalid()
	}
	result := make([]byte, 10, 10+len(compressed)+8)
	copy(result, []byte{0x1f, 0x8b, 8, 0, 0, 0, 0, 0, 2, 0xff})
	result = append(result, compressed...)
	result = binary.LittleEndian.AppendUint32(result, crc32.ChecksumIEEE(raw))
	result = binary.LittleEndian.AppendUint32(result, uint32(size))
	return result, nil
}
