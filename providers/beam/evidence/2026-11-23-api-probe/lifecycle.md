# Beam sandbox lifecycle probe results

Measured 2026-11-23 against the Beam sandbox gRPC API using the installed `beta9` SDK. Traces are redacted JSONL in this directory. TTL expiration was polled every second. All created probe sandboxes were named `probe-<run>` and stopped after measurement.

## 1. `SandboxStatus(container_id, pid=0)` and deleted IDs

- Running: the request returned `PodSandboxStatusResponse(ok=True, status='running', exit_code=-1)`; the omitted protobuf `error_msg` is the empty string. Evidence: `traces/life_ttl-ac90a006.jsonl`.
- Stopping: after `StopContainer`, the response was `PodSandboxStatusResponse(ok=True, status='stopping', exit_code=-1)` (`error_msg=''`). Evidence: `traces/life_lifecycle-39f3516a.jsonl`.
- Exited: at +4.973 s from `StopContainer`, the response was `PodSandboxStatusResponse(ok=True, status='exited', exit_code=560)` (`error_msg=''`). At +59.972 s it was the same. Evidence: `traces/life_lifecycle-39f3516a.jsonl`.
- At +600.028 s, the first observed response was `PodSandboxStatusResponse(error_msg='Failed to get sandbox status')`. Protobuf defaults give `ok=False`, `status=''`, `exit_code=0`; error text is exactly `Failed to get sandbox status`. The SDK retried this response for 120 s before raising `ConnectionError('Failed to get sandbox status')`. A raw one-call check of the deleted ID confirmed the same fields; evidence: `traces/life_lifecycle-39f3516a.jsonl` and `traces/life_unknown-4171d756.jsonl`.
- The deleted ID after 10 minutes, `sandbox-doesnotexist-0000`, and valid-looking ID `sandbox-123e4567-e89b-42d3-a456-426614174000-abcdef12` all returned `ok=False`, `status=''`, `exit_code=0`, `error_msg='Failed to get sandbox status'`. A deleted sandbox is not distinguishable from an ID that never existed by this call. Evidence: `traces/life_unknown-4171d756.jsonl`.

## 2. `StopContainer` repeated and unknown ID

- On the same real ID twice: first response `StopContainerResponse(ok=True, error_msg='')`; second `StopContainerResponse(error_msg='Unable to stop container: sandbox-b70d9420-eded-4e2e-b15d-2f79d1ad3c22-e094d475')`, whose omitted `ok` defaults to false. Evidence: `traces/life_lifecycle-39f3516a.jsonl`.
- On `sandbox-doesnotexist-0000` twice: both responses were `StopContainerResponse(ok=True, error_msg='')`. Evidence: `traces/life_unknown-4171d756.jsonl`.

## 3. TTL expiration and `update_ttl`

- Requested 45 s: `CreatePod` return to first polled `exited` status was 45.532 s, a +0.532 s gap. Response: `PodSandboxStatusResponse(ok=True, error_msg='', status='exited', exit_code=558)`.
- Requested 90 s: elapsed 91.175 s, a +1.175 s gap; same exited response with code 558.
- Updated 45 → 90 s at +15.000 s: `SandboxUpdateTTL(ttl=90)` returned `PodSandboxUpdateTtlResponse(ok=True)`. Exit was 91.409 s after update (+1.409 s) and 106.429 s after create.
- Updated 90 → 45 s at +15.000 s: `SandboxUpdateTTL(ttl=45)` returned `PodSandboxUpdateTtlResponse(ok=True)`. Exit was 47.142 s after update (+2.142 s) and 62.164 s after create.

Evidence for all four timings and update responses: `traces/life_ttl-ac90a006.jsonl`.

## 4. `keep_warm_seconds=-1` and high TTL values

- With `keep_warm_seconds=-1`, initial status was `(-1, 'pending')`; after 10.024 s it was `(-1, 'running')`. This shows it remained running during the observation window; indefinite lifetime is not determined. Evidence: `traces/life_ttl-ac90a006.jsonl`.
- Stub preparation accepted each tested value: 86,400, 604,800, and 10,000,000 seconds. Each logged `accepted=true` after `GetOrCreateStubResponse(ok=True, stub_id=...)`; no pod was created for these tests. The highest tested stub TTL was 10,000,000 seconds; the actual maximum is not determined. Evidence: `traces/life_ttl-ac90a006.jsonl`.

## 5. Exec semantics

- Fast `wait=True` returned inline: `PodSandboxExecResponse(ok=True, error_msg='', pid=14, done=True, exit_code=23, stdout='inline-out\n', stderr='inline-err\n')` in 0.209 s.
- `wait=True` for `sleep 30` returned in 0.774 s as `PodSandboxExecResponse(ok=True, error_msg='', pid=17, exit_code=-1)`; omitted `done` defaults to false, and stdout/stderr were empty. The process remained running, then status became exited after 29.591 s. The SDK `exec(..., wait=True)` also returned in 0.761 s with pid 18 and exit code -1. Thus `wait=True` can return before the process finishes; poll the pid when `done` is false. Evidence: `traces/life_exec-13a9f863.jsonl`.
- `sh -c 'exit 37'` completed with exit code 37 and empty stderr.
- Missing executable raised `SandboxProcessError('exec: "beam-life-command-that-does-not-exist": executable file not found in $PATH')`.
- Missing cwd `/beam-life-cwd-that-does-not-exist` raised `SandboxProcessError('fork/exec /usr/bin/pwd: no such file or directory')`.
- Per-exec env `LIFE_EXEC_ENV=env-value-739` was visible to the process; exit code 0 and stdout `env-value-739`.
- Argument containing spaces and both quote types round-tripped as stdout `space and 'single' plus "double"\n`; exit code 0.
- For 2 MiB each, stdout calls returned `[2097152, 0]` bytes and stderr calls `[2097152, 0]` bytes. Neither stream was truncated. Completion was indicated by the next `ok=True` response containing an empty string.
- Binary non-UTF-8 output could not be returned: `SandboxStdoutResponse(error_msg='rpc error: code = Internal desc = grpc: error while marshaling: string field contains invalid UTF-8')` (omitted `ok` defaults false).

Evidence for these requests, responses, and errors: `traces/life_exec-13a9f863.jsonl`.

## 6. Background process, kill, and retained output

- `sleep 300` returned pid 14; before kill, pid status was `ok=True, status='running', exit_code=-1` and `SandboxListProcesses` listed pids `[12, 14]` (2 total).
- `SandboxKill(container_id=..., pid=14)` returned `PodSandboxKillResponse(ok=True)`. Afterward status was `ok=True, status='exited', exit_code=137`; process listing had 3 entries.
- Six short completed processes were then added. `SandboxListProcesses` retained 9 pids immediately and still retained the same 9 after 600.108 s. At 600.161 s after pid 19 finished, `SandboxStdout(pid=19)` still returned `PodSandboxStdoutResponse(ok=True, stdout='retained-output-0')`; a second read returned an empty stdout string.

Evidence: `traces/life_process-2016bfd3.jsonl`.

## 7. Exec runtime limit and SDK RPC timeout

- `sleep 130` started with `wait=False` and reached exited status after 131.029 s.
- `sleep 400` started with `wait=False` and reached exited status after 400.183 s. No server-side per-exec limit was observed up through 400 s.
- The installed SDK defines `SANDBOX_EXEC_RPC_TIMEOUT_SECONDS = 15` and passes it as the timeout for the `/pod.PodService/SandboxExec` gRPC call in `_exec` (`beta9/abstractions/sandbox.py` in the installed SDK, lines 74 and 1109–1125). It bounds that RPC, not the lifetime of the launched process; both longer processes completed beyond 15 s.

Evidence: `traces/life_timeout-0a2406e9.jsonl`; SDK source path and lines above.

## 8. Auth errors, resource validation, and concurrency

- Wrong token on the `GetOrCreateStub` create step raised gRPC `StatusCode.UNAUTHENTICATED`, details exactly `invalid or missing token`.
- Wrong token on `SandboxStatus` raised gRPC `StatusCode.UNAUTHENTICATED`, details exactly `invalid or missing token`.
- Raw `GetOrCreateStub` request with `cpu=1000, memory=1000000000` returned `GetOrCreateStubResponse(err_msg='Memory must be 128GiB or less.')`; omitted `ok` defaults false. The SDK did not create a pod for this rejected request. Evidence: `traces/life_errors-5d5df4fb.jsonl`. The initial SDK-level attempt was rejected locally because its CPU argument is expressed in cores; the recorded raw request above reached Beam with the requested wire values. A local `NameError` in the probe's error handler occurred after this recorded response; the trace also records cleanup with no owned running IDs.
- Three simultaneous probe sandboxes all reached `RUNNING`; `ListContainersResponse` had `ok=True`, and the filtered own count was 3. All three were then stopped. The concurrency-cap rejection response is not determined because testing a fourth live sandbox would exceed the task’s three-sandbox limit. Evidence: `traces/life_concurrency-75a671ab.jsonl`.

## 9. Create latency

Not determined: no five-create median or CreatePod-to-first-successful-exec median was measured. BoxRouter’s provider-run rules require latency checks to run from a dedicated test server, which was not available for this probe. I did not substitute a local measurement. Evidence: `traces/latency-environment.jsonl`.

## 10. Final cleanup proof

Final `ListContainers` returned `ListContainersResponse(ok=True)` with no containers. The aggregate cleanup check identified all 14 probe IDs across the traces and recorded `running_own_ids=[]`, `none_of_ours_running=true`. No non-probe container was stopped. Evidence: `traces/life_final_cleanup-817ad381.jsonl`.
