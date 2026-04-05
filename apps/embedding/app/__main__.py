import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from app.server import serve

if __name__ == "__main__":
    port = int(os.environ.get("GRPC_PORT", "50051"))
    serve(port=port)
