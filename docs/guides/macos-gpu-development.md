# macOS GPU Development Safety Guide

This guide defines the required behavior when development or verification is
running on macOS and a task appears to need a CUDA-enabled PyTorch environment.
The objective is to avoid downloading or starting unusable CUDA images while
still using a faithful Apple Metal Performance Shaders (MPS) path when one
exists.

## Mandatory rule

On macOS, do not pull, build, start, or emulate a Docker target that depends on
CUDA, cuDNN, NVIDIA Container Toolkit, or a CUDA PyTorch base image. Docker
Desktop cannot expose an NVIDIA GPU to such a container. Changing the target
architecture with `--platform=linux/amd64` only adds emulation overhead; it does
not make CUDA available.

This prohibition includes indirect pulls caused by Docker Compose or a
multi-stage build. Inspect the selected service, target, and all ancestor stages
before running the command.

Examples that must not be run on macOS include:

```text
docker compose --profile gpu up
docker pull pytorch/pytorch:<version>-cuda<version>-cudnn<version>-runtime
docker build --platform=linux/amd64 --target prod -f apps/api/Dockerfile.prefect-worker-gpu .
```

A build target is allowed only if the selected target and every ancestor are
non-CUDA. For example, a standalone Go builder stage may be built when it does
not inherit from or cause Docker to pull the later CUDA/PyTorch stage.

## Decision procedure

1. Confirm the host operating system before a GPU-related dependency install,
   image pull, image build, or service start. Treat `Darwin` as macOS.
2. Inspect the requested Dockerfile/Compose target and dependency declarations
   for CUDA, cuDNN, NVIDIA, CUDA-specific PyTorch wheels, NCCL, or custom CUDA
   extensions.
3. If the task can run natively, use a host Python environment with an
   MPS-compatible PyTorch build and explicit `mps` device selection. Verify MPS
   availability before starting the workload:

   ```python
   import torch

   if not torch.backends.mps.is_available():
       raise RuntimeError("This macOS host has no usable PyTorch MPS backend")
   device = torch.device("mps")
   ```

4. Use a CPU or fake trainer/predictor only when the task is explicitly about
   orchestration, contracts, data materialization, bounded streaming, or other
   behavior that does not require CUDA correctness. State that the result does
   not validate CUDA.
5. If the workload requires CUDA-specific behavior and has no faithful MPS
   implementation, stop immediately. Do not try additional Docker flags,
   architecture emulation, repeated pulls, or a CUDA container without GPU
   access.
6. Hand the remaining verification to a Linux host or CI runner with an NVIDIA
   GPU, compatible driver, NVIDIA Container Toolkit, and the repository's
   pinned CUDA/PyTorch environment.

## What counts as an MPS workaround

An MPS workaround is acceptable only when it exercises the behavior needed by
the task. Typical candidates include model forward/backward passes supported by
PyTorch MPS, single-device training, preprocessing, materialization, and local
worker orchestration.

MPS is not a substitute for validating:

- CUDA kernels or CUDA-only custom extensions;
- NCCL or multi-GPU behavior;
- NVIDIA driver/container integration;
- CUDA memory characteristics or CUDA throughput targets;
- numerical behavior known to differ between MPS and CUDA.

For these cases, stop on macOS and record the exact Linux/NVIDIA command that
remains to be run.

## Required blocker report

When stopping, report:

- the CUDA-dependent command that was intentionally not run;
- why MPS, CPU, or fake kernels would not faithfully verify the requirement;
- the required Linux/NVIDIA execution environment;
- any non-CUDA checks that were completed successfully.

Do not describe a successful MPS or CPU check as a successful CUDA image or GPU
runtime verification.
