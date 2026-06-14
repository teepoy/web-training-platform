FROM --platform=linux/amd64 debian:bookworm-20241223-slim AS runtime-base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libvips42 \
    libglib2.0-0 \
    libexpat1 \
    libjpeg62-turbo \
    libpng16-16 \
    libwebp7 \
    libtiff6 \
    libheif1 \
    liblcms2-2 \
    libimagequant0 \
    libcgif0 \
    libexif12 \
    libspng0 \
    libopenjp2-7 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM --platform=linux/amd64 golang:1.25.5-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    libvips-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY go.work go.work.sum ./
COPY protos/gen/go/ ./protos/gen/go/
COPY services/image-parser/ ./services/image-parser/

WORKDIR /app/services/image-parser
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /server ./cmd/server/
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /seed   ./cmd/seed/ || true
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /bench  ./cmd/bench/ || true

FROM runtime-base
COPY --from=builder /server /usr/local/bin/server
COPY --from=builder /seed   /usr/local/bin/seed
COPY --from=builder /bench  /usr/local/bin/bench

EXPOSE 8090 9092
CMD ["/usr/local/bin/server"]
