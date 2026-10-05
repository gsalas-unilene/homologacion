# FastEmbed local embeddings (replaces Ollama in the preparer)

Objective: the supervised preparer (`poblar_catalogo.py`) computes catalog vectors locally with FastEmbed (ONNX, CPU) and writes them to LanceDB. The MCP stays a read-only LanceDB vector comparison with no embedder.

Problem: the configured Ollama host went down (T6 preflight timeout, Engram #1010). Ollama must not be used in this change.

Why: the user's machine is an Intel Core Ultra 7 255U running WSL2 with about 3 GiB of available RAM. Exploration evidence:
- `/dev/dxg` exists but `/dev/accel` does not, so the NPU is not reachable from WSL2.
- The OpenVINO execution provider (iGPU/NPU) supports Python 3.10-3.13 only; the project requires Python >=3.14. FastEmbed 0.8.1 installs on 3.14 with onnxruntime 1.30 and exposes only `CPUExecutionProvider`.
- Benchmark on 256 real items (avg 99 chars, 8 threads):
  - `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: 384d, 0.22 GB, 68 txt/s, about 11 min for 45673 rows, 0.9 GB RSS. Output is NOT unit-normalized (norm 2.8).
  - `jinaai/jina-embeddings-v2-base-es`: 768d, 0.64 GB, 15 txt/s, about 49 min, 1.6 GB RSS, normalized.
  - `multilingual-e5-large` and `jina-embeddings-v3` (2.2 GB) were rejected for RAM.
- MCP is already decoupled: `mcp_server.py` embeds nothing; `buscar_candidatos` reuses stored MINSA vectors and searches the internal table with the default (L2) metric. L2 ranking equals cosine only for unit vectors, so the preparer must normalize.

Scope: preparer config, embedding call, tests, README, dependency. Not in scope: Ollama code, query-time embedding in the MCP, NPU/iGPU acceleration (blocked by WSL2 and Python 3.14), commits or pushes.

Constraints: agent tools never read the real `.env`; `.env.example` is tool-blocked; no online embedding in the MCP; strict TDD disabled by the prior user choice for this feature line (functional focused tests, no RED/GREEN claims); delivery strategy `ask-on-risk`, no commit without asking.

Default model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (urgent unblock). `jinaai/jina-embeddings-v2-base-es` is the allowed quality upgrade, selected with `FASTEMBED_MODEL`.

## Tasks
- [x] F1 — Add `fastembed` dependency (`uv add fastembed`), update `uv.lock`. Route: delegated writer.
- [x] F2 — Replace Ollama in `poblar_catalogo.py`: `FASTEMBED_MODEL` allowlist config (process env, then `.env`, preparer only), local `TextEmbedding` call with bounded batches, L2 normalization, same output validation, remove urllib/Ollama code. Route: delegated writer.
- [x] F3 — Rewrite `tests/test_preparacion.py` Ollama fakes to a fake embedder; add a test that `mcp_server` does not import `fastembed`; update README (preparer section, no Ollama). Route: delegated writer.
- [ ] F4 — Supervised bulk index (replaces old T6): sample preflight, bulk index, manifest counts, one MCP lookup. Needs user authorization (model download, about 11 min CPU). Route: bounded supervised operation.

## Evidence and limitations
- F1-F3 (delegated writer, route: delegated direct because 2+ non-trivial files). Parent spot check: `FASTMCP_ENV_FILE=/dev/null uv run --frozen python -m unittest discover -s tests` -> 29 tests OK; `grep -i ollama` over code, tests, README and pyproject returns nothing; `fastembed>=0.8.1` declared.
- Writer also ran `uv sync --frozen` (OK). No real model download, indexing or `.env` read happened in this change.
- Limitations: no independent verifier run; no real-model smoke test through the project cache dir yet (benchmark used a scratch venv); no commit (all files untracked, ask-on-risk).
- Old T6 in `offline-homologacion-mcp.md` is superseded by F4.

## OS change: WSL2 to native Windows (decided by the user, 2026-10-02)

Why: WSL2 cannot drive the Intel NPU (no `/dev/accel`; NPU is enumerable but not driveable, microsoft/WSL#40445, #40842). The iGPU is technically reachable in WSL2 but needs `sudo apt` packages. Native Windows exposes CPU, iGPU and NPU to OpenVINO.

Verified facts that shape the scope:
- `onnxruntime-openvino` 1.24.1 ships `win_amd64` wheels for cp311, cp312 and cp313 only. The project currently pins Python >=3.14, so the Windows environment must use Python 3.13 and `requires-python` must be lowered (W2).
- `onnxruntime-openvino` and `onnxruntime` both provide the `onnxruntime` module: install one, not both. `fastembed` depends on `onnxruntime`, so swap it manually after `uv sync`.
- The NPU accepts static shapes only. Transformer embedding models run with dynamic batch and sequence length, so the NPU needs fixed padding (for example 64 or 128 tokens, fixed batch) or the provider option `disable_dynamic_shapes`. The iGPU accepts dynamic shapes.
- Not verified: real speed-up on this machine, and whether FastEmbed's tokenizer pipeline can feed fixed shapes without bypassing it.

Tasks (all pending):
- [ ] W1 — Move the repo to a Windows folder with the same directory name `homologador` (Engram derives the project name from the git root). Import Engram, create a fresh `.env` there, run the suite on Windows. Route: user + inline.
- [ ] W2 — Set `.python-version` to 3.13 and `requires-python = ">=3.13"`, run `uv lock`, rerun the suite. Route: inline (small edit, one verification).
- [ ] W3 — Device probe and benchmark: list OpenVINO devices (`openvino.Core().available_devices`, expect CPU, GPU, NPU) and rerun the 256-item benchmark per device with MiniLM. CPU baseline from WSL: 68 texts/s. Route: bounded supervised operation, throwaway script outside the repo.
- [ ] W4 — Optional `FASTEMBED_DEVICE` (cpu default, gpu, npu) in `poblar_catalogo.py` through FastEmbed `providers`, with fixed padding for NPU and fallback NPU -> GPU -> CPU. Only if W3 shows at least 2x over CPU and cosine similarity of at least 0.99 against CPU vectors on the sample; otherwise keep CPU and close W4 as not needed. Route: delegated writer.
- [ ] W5 — F4 on Windows: supervised sample, bulk index of 22668 internal and 23005 MINSA rows with the chosen device, manifest counts, one MCP lookup. Needs fresh user authorization (about 0.22 GB model download). Route: bounded supervised operation.

Quick start on Windows (PowerShell), in order:
1. Copy the whole folder including `.git` (or `git clone` from the WSL path) into e.g. `C:\dev\homologador`; keep the folder name. Branch: `feat/offline-homologacion-mcp`.
2. `engram sync --import` inside that folder (reads `.engram/` chunks committed in this repo). Check with `engram search "fastembed"`. If the project name differs, `.engram/config.json` pins `homologador`.
3. Install Python 3.13 and uv: `uv python install 3.13`, then `uv sync`.
4. Run the suite: `$env:FASTMCP_ENV_FILE="NUL"; uv run python -m unittest discover -s tests` (no `-t .`). Expected: 29 tests OK. If a test hardcodes `/dev/null`, fix it as part of W1.
5. Do W2, then W3 (`uv pip uninstall onnxruntime`, `uv pip install onnxruntime-openvino openvino`), then decide W4, then W5.
6. Rebuild the CodeGraph index in the new folder (`.codegraph/` is git-ignored and must not be copied).

Do not store the real `.env` in git. `datos_medicos_db/` and `.fastembed_cache/` are git-ignored and regenerated by the preparer.

Next: W1 by the user, then W2-W3 in the first Windows session.
