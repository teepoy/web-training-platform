# Worker

Prefect flow-worker package.

This package runs Prefect queue workers for delegated training and batch runtime
flows. It is separate from `apps/inference`, which is the HTTP inference service
that serves `/v1/predict` and `/v1/embed` requests.
