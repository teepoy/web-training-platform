FROM golang:1.26-alpine AS build-base

FROM build-base AS builder
ARG TARGETOS
ARG TARGETARCH
WORKDIR /app
COPY services/image-parser/go.mod services/image-parser/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY services/image-parser/ ./
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" \
    go build -ldflags="-s -w" -o /server ./cmd/server/

FROM build-base AS dev
WORKDIR /app/services/image-parser
RUN go install github.com/air-verse/air@v1.63.0
CMD ["air", "-c", ".air.toml"]

FROM alpine:3.23 AS runtime

RUN apk add --no-cache ca-certificates

COPY --from=builder /server /usr/local/bin/server
EXPOSE 8090 9092
CMD ["/usr/local/bin/server"]
