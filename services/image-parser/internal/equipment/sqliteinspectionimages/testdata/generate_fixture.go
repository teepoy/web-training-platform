//go:build ignore

package main

import (
	"bytes"
	"database/sql"
	"encoding/binary"
	"fmt"
	"os"

	"github.com/golang/snappy"
	_ "modernc.org/sqlite"
)

func main() {
	if len(os.Args) != 2 {
		panic("usage: go run generate_fixture.go OUTPUT.sqlite")
	}
	path := os.Args[1]
	if _, err := os.Stat(path); err == nil {
		panic(fmt.Sprintf("refusing to overwrite %s", path))
	} else if !os.IsNotExist(err) {
		panic(err)
	}
	database, err := sql.Open("sqlite", path)
	if err != nil {
		panic(err)
	}
	if _, err := database.Exec(`
		CREATE TABLE inspection_images (
			id INTEGER PRIMARY KEY,
			defect_id INTEGER NOT NULL,
			image_type TEXT NOT NULL,
			image_id INTEGER,
			image_value BLOB NOT NULL
		)
	`); err != nil {
		panic(err)
	}
	rows := []struct {
		imageType string
		imageID   *int
		value     []byte
	}{
		{imageType: "T", value: encodeU16(100, 3500)},
		{imageType: "R", imageID: intPointer(0), value: encodeU16(200, 3000)},
		{imageType: "R", imageID: intPointer(1), value: encodeU16(300, 3200)},
		{imageType: "D", imageID: intPointer(0), value: encodeU16(10, 1000)},
		{imageType: "D", imageID: intPointer(1), value: encodeU16(20, 2000)},
		{imageType: "M", imageID: intPointer(0), value: encodeU8(0, 1)},
	}
	for index, row := range rows {
		if _, err := database.Exec(
			"INSERT INTO inspection_images(id, defect_id, image_type, image_id, image_value) VALUES (?, ?, ?, ?, ?)",
			index+1, 42, row.imageType, row.imageID, row.value,
		); err != nil {
			panic(err)
		}
	}
	if err := database.Close(); err != nil {
		panic(err)
	}
}

func encodeU16(minimum, maximum uint16) []byte {
	raw := make([]byte, 32*32*2)
	for index := range 32 * 32 {
		value := minimum
		if index == 1 {
			value = maximum
		}
		binary.BigEndian.PutUint16(raw[index*2:index*2+2], value)
	}
	return append([]byte{0x2e, 0x9c}, snappy.Encode(nil, raw)...)
}

func encodeU8(minimum, maximum byte) []byte {
	raw := bytes.Repeat([]byte{minimum}, 32*32)
	raw[1] = maximum
	return append([]byte{0x2e, 0x9c}, snappy.Encode(nil, raw)...)
}

func intPointer(value int) *int { return &value }
