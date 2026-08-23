package sqliteinspectionimages

import (
	"encoding/binary"
	"strings"
	"testing"

	"github.com/golang/snappy"
)

func TestDecodeSnappyImageRejectsValuesOutsideFixedTwelveBitContract(t *testing.T) {
	raw := make([]byte, imageWidth*imageHeight*2)
	binary.BigEndian.PutUint16(raw[:2], 4096)
	value := append([]byte{0x2e, 0x9c}, snappy.Encode(nil, raw)...)

	_, err := decodeSnappyImage(value)
	if err == nil || !strings.Contains(err.Error(), "exceeds 4095") {
		t.Fatalf("error = %v", err)
	}
}
