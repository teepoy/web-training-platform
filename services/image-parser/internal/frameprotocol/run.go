// Package frameprotocol owns the bounded stdin/stdout protobuf transport shared
// by job-local and pure-local resolver processes.
package frameprotocol

import (
	"bufio"
	"context"
	"encoding/binary"
	"errors"
	"fmt"
	"io"

	"google.golang.org/protobuf/proto"
	imageparserv1 "image-parser/gen/go/imageparser/v1"
	imageloader "image-parser/internal/image_loader"
	"image-parser/internal/service"
)

const MaxFrameBytes = 256 * 1024 * 1024

func Run(ctx context.Context, input io.Reader, output io.Writer, images imageloader.ImageLoader) error {
	reader := bufio.NewReader(input)
	writer := bufio.NewWriter(output)
	for {
		var size uint32
		if err := binary.Read(reader, binary.BigEndian, &size); err != nil {
			if errors.Is(err, io.EOF) {
				return nil
			}
			return fmt.Errorf("read request frame size: %w", err)
		}
		if size == 0 || size > MaxFrameBytes {
			return fmt.Errorf("request frame size %d is outside (0, %d]", size, MaxFrameBytes)
		}
		payload := make([]byte, size)
		if _, err := io.ReadFull(reader, payload); err != nil {
			return fmt.Errorf("read request frame: %w", err)
		}
		request := &imageparserv1.ResolvePatchImagesRequest{}
		if err := proto.Unmarshal(payload, request); err != nil {
			return fmt.Errorf("decode request frame: %w", err)
		}
		response, err := service.ResolvePatchImagesBatch(ctx, images, request)
		if err != nil {
			return fmt.Errorf("resolve request frame: %w", err)
		}
		responsePayload, err := proto.Marshal(response)
		if err != nil {
			return fmt.Errorf("encode response frame: %w", err)
		}
		if len(responsePayload) > MaxFrameBytes {
			return fmt.Errorf("response frame size %d exceeds %d", len(responsePayload), MaxFrameBytes)
		}
		if err := binary.Write(writer, binary.BigEndian, uint32(len(responsePayload))); err != nil {
			return fmt.Errorf("write response frame size: %w", err)
		}
		if _, err := writer.Write(responsePayload); err != nil {
			return fmt.Errorf("write response frame: %w", err)
		}
		if err := writer.Flush(); err != nil {
			return fmt.Errorf("flush response frame: %w", err)
		}
	}
}
