# Beam sandbox probe findings

Measured 2026-11-23 with the installed Python `beta9` SDK. All RPC traces are in `../beam-probe/traces/`; the traces redact credentials and presigned URLs.

## 1. `SandboxUploadFile`

- **Request limit:** gRPC rejects serialized messages over 16,777,216 bytes. For the fixed request in `data_upload_boundary-05377965.jsonl`, `data=16,777,119` serialized to exactly `16,777,216` and returned `ok=True`; one more data byte serialized to `16,777,217` and raised `RESOURCE_EXHAUSTED: CLIENT: Sent message larger than max (16777217 vs. 16777216)`. This is the exact maximum for that request shape; the available data bytes vary with the other fields. A 16 MiB payload failed (`16777313 vs. 16777216`) in `data_files-d58ae364.jsonl`.
- **Offsets and mode:** offset 0 created `abcdef` with mode `0o600`; offset 6 appended `ghi`; offset 1 overwrote bytes to produce `aXYdefghi`; offset 0 with mode `0o640` replaced/truncated the file to `Q` and changed its mode to `0o640`. Creating a new file at offset 9 with `tail` succeeded and zero-filled the nine-byte hole. Trace: `data_files-d58ae364.jsonl`.
- **Missing parent and directory target:** SDK `fs.write_text()` to a missing nested parent succeeded and stat confirmed the parent and child; a raw upload request targeting an existing directory returned `ok=True` and created a one-byte child named `upload_<uuid>`. The direct raw-RPC behavior for a missing parent was not isolated. Traces: `data_files-d58ae364.jsonl`, `data_file_followup-b0bfbbef.jsonl`.
- **SDK transfer shape:** `_upload` sends 4 MiB chunks to a temporary sibling path, then runs `sha256sum` and `mv` via `SandboxExec` (with status/stdout polling); it rejects a mismatch before renaming. The 16 MiB upload used four `SandboxUploadFile` RPCs. The staged-file `sha256sum` output matched the local SHA-256 `4dc59d29ac26a648779bea0089284060c55bc39d5e5782473a5bbd27636db219`; the final `mv` RPC succeeded. The probe's separate post-rename checksum read returned no stdout, so it did not establish an independent hash after rename. Trace: `data_files-d58ae364.jsonl`; implementation: `../beam-probe/v/lib/python3.15/site-packages/beta9/abstractions/sandbox.py` (`_upload`, around line 1896).
- **Throughput:** random 16 MiB upload took 6.1289 s (2.611 MiB/s), with the SDK checksum and rename succeeding. The 128 MiB and 1 GiB transfer timings and completion are **not determined**: the devbox has no AWS test-server profile/helper, which the probe rules require for transfers over about 100 MiB, so those transfers were not attempted. Thus 1 GiB completion under the message cap is also **not determined**.
- **Time limit:** SDK upload/download calls use a 120 s `rpc_timeout` (`RECOVERY_TIMEOUT`) per transfer operation. This is an SDK deadline, not a measured Beam server limit. Direct raw RPC calls in the probes did not set an explicit deadline. Implementation: `../beam-probe/v/lib/python3.15/site-packages/beta9/abstractions/sandbox.py` and `../beam-probe/v/lib/python3.15/site-packages/beta9/channel.py`.

## 2. `SandboxDownloadFile`

- For a ten-byte file containing `0123456789`, `(offset=3,length=4)` returned `3456`; `(7,20)` returned `789`; offsets at EOF and past EOF returned `ok=True` with empty data. `length=0` means read through EOF: `(3,0)` returned `3456789`. Trace: `data_file_ranges-e2a7601a.jsonl`.
- A 4 MiB request succeeded. Requests larger than 4 MiB returned `Invalid download range (maximum chunk: 4 MiB)`. A zero-length request against the 16 MiB file attempted the whole remainder and exceeded the gRPC response cap: `grpc: trying to send message larger than max (16777223 vs. 16777216)`. Trace: `data_files-d58ae364.jsonl`.
- SDK `_download` requests 4 MiB ranges and continues until a short response. The 16 MiB download used four 4 MiB responses plus an empty EOF response (5 RPCs), took 4.054 s (3.947 MiB/s), and its local SHA-256 matched the source hash above. Writing yielded chunks directly to a local file uses memory bounded by the 4 MiB chunk; `read_bytes()` instead joins the full file in memory. The 128 MiB and 1 GiB throughput/RPC counts are **not determined** for the same missing test-server fixture reason as item 1. Trace: `data_files-d58ae364.jsonl`.
- Missing-file SDK error: `failed to read file from /tmp/probe-d58ae364-missing: openat tmp/probe-d58ae364-missing: no such file or directory`. Reading `/tmp` returned `is a directory`. The full SDK errors are in `data_files-d58ae364.jsonl`.
- A same-size file mutation between two 4 MiB range calls returned the original `A` bytes in the first range and `B` in the second, with both calls `ok=True` and no error; there is no observed read snapshot/version check. Trace: `data_files-d58ae364.jsonl`.

## 3. Read after stop

Immediately after `StopContainer`, while the sandbox was still stopping, a direct 32-byte `SandboxDownloadFile` request succeeded with 15 bytes. After polling status to `exited` (`stopping`, `stopping`, `exited` in 0.2948 s), the direct request raised `ConnectionError: Failed to connect to sandbox`. The exited-state attempt reached its error after the SDK retry window. Traces: `data_file_followup-b0bfbbef.jsonl`, `data_file_boundary_stop-fdf15853.jsonl`.

## 4. Filesystem listing, stat, directories and deletes

- `SandboxFileInfo` exposes `name`, `is_dir`, `size`, `mode`, `mod_time`, `permissions`, `owner`, and `group`. `permissions` is an integer, not a string: e.g. 384 (`0o600`) and 420 (`0o644`). `mode` is signed; directory mode values appeared negative because of the type bit. `mod_time` is Unix epoch seconds (sample: `1795426747`); owner/group were strings `"0"`. Trace: `data_files-d58ae364.jsonl`.
- The observed listing order was lexical: `a.txt`, `b.txt`, `c.txt`, `dangling`, `link`. Listing reports symlink entries themselves (`is_dir=False`, symlink mode); it includes a dangling symlink. `stat_file()` follows a valid symlink (reported its target size 2 and mode `0o644`); stat of the dangling symlink returned `no such file or directory`. Trace: `data_files-d58ae364.jsonl`.
- `create_directory(".../a/b/c")` created missing parents. `delete_directory()` on a non-empty directory returned normally and removed the directory and its child. Deleting nonexistent file and directory paths also returned normally; follow-up stat confirmed they remained absent. Traces: `data_files-d58ae364.jsonl`, `data_file_followup-b0bfbbef.jsonl`.

## 5. Large command output

The sandbox process generated 16 MiB of stdout and exited, but its first `SandboxStdout` response failed with `RESOURCE_EXHAUSTED: grpc: received message larger than max (16777223 vs. 16777216)`. No stdout page was returned. The SDK stream fetches repeated unary `SandboxStdout` deltas, but this single 16 MiB response exceeded the client receive cap before it could be consumed. Truncation and the total output cap are **not determined**; the evidence shows a failed oversized response, not a byte cutoff. The 64 MiB case was not reached. Trace: `data_output-a8c7e98f.jsonl`.

## 6. `expose_port` and `list_urls`

- The URL form was `https://<container_id>-<port>.app.beam.cloud` (the container ID itself starts `sandbox-...`), with an empty path and no userinfo. TLS verification succeeded (`ssl_verify_result=0`, HTTP/1.1). With `authorized=False`, curl without credentials returned HTTP 200; first 200 arrived after 0.6213 s from exposure (one poll). Trace: `data_network-369b6844.jsonl`.
- With `authorized=True`, unauthenticated curl returned HTTP 400. A bearer-token request held only in memory returned HTTP 200 on its first poll, 0.6479 s after exposure; the probe never logged the token. Traces: `data_network-369b6844.jsonl`, `data_network_authorized-d24b6d43.jsonl`, `data_network_auth_poll-8a51346c.jsonl`.
- `expose_port(8000)` returned in 0.1017 s. 65 calls for ports 8000–8064 succeeded with no exception, but `list_urls()` returned 64 entries and omitted port 8001. The exact port limit/reason is **not determined**. Trace: `data_network-369b6844.jsonl`.
- There was no individual unexpose method/RPC in the installed SDK/service stubs. Terminating the sandbox stopped the URL: the unauthenticated public URL returned 503; the authorized URL returned 503 when called with its bearer token. Therefore termination revoked access in these probes. Traces: `data_network-369b6844.jsonl`, `data_network_authorized-d24b6d43.jsonl`.

## 7. Outbound network permissions

- Default outbound HTTPS to `https://example.com` succeeded (curl exit 0, HTTP 200).
- `update_network_permissions(block_network=True)` on a running sandbox blocked outbound HTTPS: curl exit 28, HTTP 000, `Resolving timed out after 10000 milliseconds`; the inbound exposed URL still returned HTTP 200.
- A subsequent runtime `update_network_permissions(allow_list=["example.com"])` allowed `example.com` (HTTP 200); `example.org` failed (curl exit 35, HTTP 000, TLS `unexpected eof while reading`). Runtime update therefore worked without restart. Trace for all three: `data_network-369b6844.jsonl`.
- The sandbox SDK constructor accepts `block_network` and `allow_list`; create-time restriction behavior was not separately live-tested. Beam's docs say exposed URLs remain inbound-accessible when outbound traffic is blocked, runtime changes close existing connections, and the allowlist supports up to 64 entries: [Networking docs](https://docs.beam.cloud/v2/sandbox/networking.md).

## 8. Public registry images and credentials

- `Image.from_registry()` built and ran all three public images. `Image.build()` used unary `VerifyImageBuild` followed by a `BuildImage` response stream; sandbox creation then used the normal pod creation calls. Cold build times: `ubuntu:24.04` 59.3914 s, `python:3.12-slim` 45.808 s, `node:20` 48.0101 s. The warm Ubuntu build returned the same image ID with `exists=True` and took 0.0212 s. Traces: `data_images-aedd8777.jsonl` (build stream events and results).
- Runtime: all three ran as uid 0 in `/workspace` with `/usr/bin/bash`. Ubuntu 24.04 had no `python3` or `node` found by `command -v`; Python slim had `/usr/local/bin/python3` and no `node`; Node 20 had `/usr/bin/python3`, `/usr/local/bin/node`, and reported `v20.20.2`.
- Private registries were not exercised. SDK source supports `Image.from_registry(uri, credentials=[workspace_secret_names])`; the request sends those names in `existing_image_creds`. The source lists Docker Hub, registry username/password, AWS ECR keys, GitHub, GCP and NGC credential keys. No real credentials were used. Source: `../beam-probe/v/lib/python3.15/site-packages/beta9/abstractions/image.py` and `../beam-probe/v/lib/python3.15/site-packages/beta9/clients/image/__init__.py`.

## 9. Snapshots

- `create_image_from_filesystem()` issued `/pod.PodService/SandboxCreateImageFromFilesystem`, took 4.768 s, and returned image ID `5270ee9f-9c88-4863-829b-8b002ee49474-1795428215` (UUID plus epoch-seconds suffix). Restoring with `Image.from_id()` preserved the marker file but did not restore the original sleeping process.
- `snapshot_memory()` issued `/pod.PodService/SandboxSnapshotMemory`, took 0.665 s, and returned checkpoint ID `259eb802-59a3-44f5-9c43-9828f9062bfe`. `create_from_memory_snapshot()` issued `CreatePod` with that checkpoint and took 0.0392 s; the restored sandbox resumed PID 13 and its counter advanced from 8 to 9.
- Deletion is **not determined**: no snapshot/image delete method was present in the installed SDK or service stubs, and the docs page gives no deletion procedure; no deletion was attempted. The snapshot docs say storage is not billed yet and planned pricing is $0.0001 per GB-hour, with no free allowance (1 GB = 1 billion bytes); retained snapshot data is included. No size/retention limit was listed on that page: [Snapshots docs](https://docs.beam.cloud/v2/sandbox/snapshots.md).
- Trace: `data_snapshots-b6f15169.jsonl`.

## 10. Cleanup proof

- Each completed probe's `ListContainers` cleanup record has `own_running=[]`. The one initial image-script failure (`data_images-9bfd2261.jsonl`) created no sandbox (`CreatePod` count 0).
- Final aggregate `ListContainers` checked all 19 container IDs created by these probes: `list_ok=True`, `returned_running_count=0`, `own_running=[]`. Trace: `data_final_cleanup-02c0b686.jsonl`.
- Final filesystem check found no `/dev/shm/beam-*` transfer temp files. The filesystem image and memory checkpoint IDs above have no delete method found, so their artifact retention remains unresolved.
