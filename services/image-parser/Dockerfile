FROM --platform=linux/amd64 golang-vips:base AS builder

WORKDIR /app

COPY go.work go.work.sum ./
COPY protos/gen/go/ ./protos/gen/go/
COPY services/image-parser/ ./services/image-parser/

WORKDIR /app/services/image-parser
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /server ./cmd/server/
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /seed   ./cmd/seed/ || true
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /bench  ./cmd/bench/ || true

FROM golang-vips:base
COPY --from=builder /server /usr/local/bin/server
COPY --from=builder /seed   /usr/local/bin/seed
COPY --from=builder /bench  /usr/local/bin/bench

EXPOSE 8090 9092
CMD ["/usr/local/bin/server"]
