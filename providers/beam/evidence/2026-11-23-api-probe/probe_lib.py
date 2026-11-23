"""Tracing library for live Beam probes: `import probe_lib` BEFORE `from beam import ...`.

It loads the token from ~/.beam-key into BEAM_TOKEN (never print it), logs every gRPC call to
`traces/<scenario>-<runid>.jsonl` with the token and presigned URLs redacted, and exposes `RUN`
(use it in every sandbox name: `probe-<RUN>`) and `log(kind, **fields)` for notes.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

os.environ.setdefault("BEAM_TOKEN", open(os.path.expanduser("~/.beam-key")).read().strip())
TOKEN = os.environ["BEAM_TOKEN"]

import beam  # noqa: E402,F401  (selects gateway.beam.cloud)
import grpc  # noqa: E402
from beta9 import channel as ch  # noqa: E402

RUN = uuid.uuid4().hex[:8]
NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]
LOG = open(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "traces", f"{NAME}-{RUN}.jsonl"),
    "w",
)
T0 = time.monotonic()


import re  # noqa: E402


def red(text: str) -> str:
    text = text.replace(TOKEN, "<token>")
    return re.sub(
        r"(presigned_url|https://[^\s'\"]*X-Amz[^\s'\"]*)",
        lambda m: "<redacted-url>" if m.group(0).startswith("https") else m.group(0),
        re.sub(r"presigned_url='[^']*'", "presigned_url='<redacted>'", text),
    )


def log(kind: str, **fields) -> None:
    fields = {"t": round(time.monotonic() - T0, 3), "kind": kind, **fields}
    LOG.write(red(json.dumps(fields, default=repr)) + "\n")
    LOG.flush()


_orig = ch.AuthTokenInterceptor.intercept_call


def traced(self, continuation, details, request):
    method = details.method
    start = time.monotonic()
    try:
        call = _orig(self, continuation, details, request)
    except Exception as e:  # noqa: BLE001
        log("rpc-error", method=method, error=repr(e)[:500])
        raise
    try:
        if hasattr(call, "result"):
            res = call.result()
            log(
                "rpc",
                method=method,
                ms=round((time.monotonic() - start) * 1000),
                request=repr(request)[:2000],
                response=repr(res)[:4000],
            )
        else:
            log("rpc-stream", method=method, request=repr(request)[:2000])
    except grpc.RpcError as e:
        log(
            "rpc-fail",
            method=method,
            ms=round((time.monotonic() - start) * 1000),
            request=repr(request)[:2000],
            code=str(e.code()),
            details=e.details(),
        )
        raise
    return call


ch.AuthTokenInterceptor.intercept_call = traced
