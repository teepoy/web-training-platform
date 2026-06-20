FROM golang:1.26-bookworm AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libvips-dev \
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

FROM base AS builder
WORKDIR /app
COPY services/image-parser/ ./
RUN CGO_ENABLED=1 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /server ./cmd/server/

FROM base AS dev
WORKDIR /app/services/image-parser
RUN go install github.com/air-verse/air@v1.63.0
CMD ["air", "-c", ".air.toml"]

FROM base
COPY --from=builder /server /usr/local/bin/server
EXPOSE 8090 9092
CMD ["/usr/local/bin/server"]
