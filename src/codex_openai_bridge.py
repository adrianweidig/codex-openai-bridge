#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


MODEL_ALIASES = {
    "coder": "gpt-5.5",
    "codex": "gpt-5.5",
}

DEFAULT_MODELS = [
    "coder",
    "codex",
    "gpt-5.5",
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.3-codex",
    "gpt-5.3-codex-spark",
]


def log_event(event: str, **fields: Any) -> None:
    record: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": event,
    }
    for key, value in fields.items():
        if value is not None:
            record[key] = value
    print(json.dumps(record, ensure_ascii=False), flush=True)


def sanitize_log_line(value: str, max_length: int = 1200) -> str:
    clean = value.replace("\r", "").strip()
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 1] + "…"


def public_codex_log_line(stream_name: str, line: str) -> str | None:
    if stream_name == "stdout":
        return None
    lower = line.lower()
    safe_prefixes = (
        "openai codex",
        "workdir:",
        "model:",
        "provider:",
        "approval:",
        "sandbox:",
        "reasoning effort:",
        "reasoning summaries:",
        "session id:",
        "warning:",
        "tokens used",
    )
    if any(lower.startswith(prefix) for prefix in safe_prefixes):
        return line
    if line == "--------" or line.replace(",", "").isdigit():
        return line
    return None


def parse_model_list(value: str | None) -> list[str] | None:
    if not value:
        return None
    models = [item.strip() for item in value.split(",") if item.strip()]
    return models or None


def read_secret_value(value: str | None, file_value: str | None) -> str | None:
    if value:
        return value
    if not file_value:
        return None
    path = Path(file_value)
    if not path.exists():
        raise FileNotFoundError(f"Secret file not found: {path}")
    return path.read_text(encoding="utf-8").strip()


def build_prompt(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = message.get("content", "")
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in {"text", "input_text"}:
                        text_parts.append(str(item.get("text") or ""))
                else:
                    text_parts.append(str(item))
            content = "\n".join(text_parts)
        parts.append(f"{role}:\n{content}")
    return "\n\n".join(parts).strip()


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in {"text", "input_text", "output_text"}:
                    text_parts.append(str(item.get("text") or ""))
                elif item.get("type") == "input_image":
                    text_parts.append("[Bildinhalt]")
            else:
                text_parts.append(str(item))
        return "\n".join(part for part in text_parts if part)
    return str(content) if content is not None else ""


def build_prompt_from_responses(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    instructions = text_from_content(payload.get("instructions"))
    if instructions:
        parts.append(f"SYSTEM:\n{instructions}")

    input_value = payload.get("input", "")
    if isinstance(input_value, str):
        if input_value.strip():
            parts.append(f"USER:\n{input_value}")
    elif isinstance(input_value, list):
        for item in input_value:
            if not isinstance(item, dict):
                text = text_from_content(item)
                if text:
                    parts.append(f"USER:\n{text}")
                continue

            item_type = item.get("type")
            if item_type == "message":
                role = str(item.get("role") or "user").upper()
                text = text_from_content(item.get("content", ""))
                if text:
                    parts.append(f"{role}:\n{text}")
            elif item_type == "function_call_output":
                call_id = item.get("call_id", "")
                parts.append(f"TOOL RESULT {call_id}:\n{text_from_content(item.get('output', ''))}")
            elif item_type == "function_call":
                name = item.get("name", "")
                arguments = item.get("arguments", "")
                parts.append(f"ASSISTANT TOOL CALL {name}:\n{arguments}")
            else:
                text = text_from_content(item)
                if text:
                    parts.append(f"USER:\n{text}")
    return "\n\n".join(parts).strip()


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def wslpath(path: Path, mode: str) -> Path:
    completed = subprocess.run(
        ["wslpath", mode, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return Path(completed.stdout.strip())


def windows_temp_pair() -> tuple[Path, str]:
    completed = subprocess.run(
        ["cmd.exe", "/c", "echo", "%TEMP%"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    windows_dir = completed.stdout.strip().replace("\\", "\\")
    linux_dir = wslpath(Path(windows_dir), "-u")
    linux_dir.mkdir(parents=True, exist_ok=True)
    return linux_dir, windows_dir


def resolve_codex_command(command: str | None, use_windows_codex: bool) -> list[str]:
    if command:
        if use_windows_codex:
            return ["cmd.exe", "/c", command]
        return [command]
    if use_windows_codex:
        return ["cmd.exe", "/c", "codex"]
    configured = os.getenv("CODEX_BRIDGE_CODEX_COMMAND")
    if configured:
        return [configured]
    if os.name == "nt":
        return [shutil.which("codex.cmd") or shutil.which("codex.exe") or "codex.cmd"]
    return [shutil.which("codex") or "codex"]


def run_codex(
    prompt: str,
    model: str,
    timeout: int,
    workdir: Path,
    codex_command: str | None,
    use_windows_codex: bool,
    request_id: str,
    progress_callback: Callable[[str], None] | None = None,
    progress_interval: int = 15,
) -> str:
    target_model = MODEL_ALIASES.get(model, model)
    temp_dir: Path | None = None
    output_arg = None
    workdir_arg = str(workdir)
    if use_windows_codex:
        temp_dir, _windows_temp_dir = windows_temp_pair()
        workdir_arg = str(wslpath(workdir, "-w"))
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", dir=temp_dir) as output:
        output_path = Path(output.name)
        output_arg = str(wslpath(output_path, "-w")) if use_windows_codex else str(output_path)
    try:
        command = [
            *resolve_codex_command(codex_command, use_windows_codex),
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--cd",
            workdir_arg,
            "-m",
            target_model,
            "-o",
            output_arg,
            "-",
        ]
        command_label = " ".join(command[:2]) if len(command) > 1 else command[0]
        log_event(
            "codex.start",
            request_id=request_id,
            model=model,
            target_model=target_model,
            timeout_seconds=timeout,
            workdir=str(workdir),
            command=command_label,
            prompt_chars=len(prompt),
        )
        if progress_callback:
            progress_callback(f"gestartet mit Modell {target_model}; warte auf Codex.")

        process = subprocess.Popen(
            command,
            cwd=workdir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        stdout_tail: list[str] = []
        stderr_tail: list[str] = []

        def read_stream(stream_name: str, stream: Any) -> None:
            try:
                for line in stream:
                    output_queue.put((stream_name, sanitize_log_line(line)))
            finally:
                output_queue.put((stream_name, None))

        readers = [
            threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
        ]
        for reader in readers:
            reader.start()

        try:
            if process.stdin:
                process.stdin.write(prompt)
                process.stdin.close()
        except BrokenPipeError:
            pass

        started_at = time.monotonic()
        next_progress = started_at + max(1, progress_interval)
        active_readers = len(readers)

        while active_readers:
            now = time.monotonic()
            if process.poll() is None and now - started_at > timeout:
                process.kill()
                elapsed = round(now - started_at, 1)
                log_event("codex.timeout", request_id=request_id, elapsed_seconds=elapsed)
                raise TimeoutError(f"codex exec timed out after {timeout} seconds")

            if progress_callback and now >= next_progress:
                elapsed = int(now - started_at)
                try:
                    progress_callback(f"läuft seit {elapsed}s; Codex verarbeitet die Anfrage noch.")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    if process.poll() is None:
                        process.kill()
                    log_event("client.disconnected", request_id=request_id, elapsed_seconds=elapsed)
                    raise
                log_event("codex.progress", request_id=request_id, elapsed_seconds=elapsed)
                next_progress = now + max(1, progress_interval)

            try:
                stream_name, line = output_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if line is None:
                active_readers -= 1
                continue
            if not line:
                continue

            if stream_name == "stdout":
                stdout_tail = (stdout_tail + [line])[-20:]
            else:
                stderr_tail = (stderr_tail + [line])[-20:]
            public_line = public_codex_log_line(stream_name, line)
            if public_line:
                log_event("codex.output", request_id=request_id, stream=stream_name, line=public_line)
            else:
                log_event("codex.activity", request_id=request_id, stream=stream_name, chars=len(line))

        returncode = process.wait(timeout=2)
        elapsed = round(time.monotonic() - started_at, 1)
        if returncode != 0:
            detail = "\n".join(stderr_tail or stdout_tail or ["codex exec failed"]).strip()
            log_event("codex.failed", request_id=request_id, returncode=returncode, elapsed_seconds=elapsed)
            raise RuntimeError(detail[-2000:])
        text = output_path.read_text(encoding="utf-8", errors="replace").strip()
        log_event(
            "codex.done",
            request_id=request_id,
            returncode=returncode,
            elapsed_seconds=elapsed,
            output_chars=len(text),
        )
        if progress_callback:
            progress_callback(f"abgeschlossen nach {elapsed}s; übertrage Antwort.")
        return text
    finally:
        output_path.unlink(missing_ok=True)


def chunk_text(value: str, size: int = 1200) -> list[str]:
    return [value[index : index + size] for index in range(0, len(value), size)] or [""]


def chat_completion_response(completion_id: str, model: str, text: str, created: int) -> dict[str, Any]:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def responses_message_item(message_id: str, text: str, status: str = "completed") -> dict[str, Any]:
    return {
        "id": message_id,
        "type": "message",
        "status": status,
        "role": "assistant",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def responses_result(response_id: str, message_id: str, model: str, text: str, created: int) -> dict[str, Any]:
    output = [responses_message_item(message_id, text)]
    return {
        "id": response_id,
        "object": "response",
        "created_at": created,
        "status": "completed",
        "model": model,
        "output": output,
        "output_text": text,
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


class CodexBridgeHandler(BaseHTTPRequestHandler):
    server_version = "CodexOpenAIBridge/0.1"

    def _json_response(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _is_authorized(self) -> bool:
        if not self.server.api_key:
            return True
        expected = f"Bearer {self.server.api_key}"
        return self.headers.get("Authorization") == expected or self.headers.get("X-API-Key") == self.server.api_key

    def _require_authorized(self) -> bool:
        if self._is_authorized():
            return True
        log_event("request.unauthorized", path=self.path)
        self._json_response(401, {"error": {"message": "Unauthorized", "type": "authentication_error"}})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/health":
            self._json_response(200, {"status": "ok", "models": self.server.models})
            return
        if not self._require_authorized():
            return
        if self.path.rstrip("/") in {"/v1/models", "/models"}:
            now = int(time.time())
            self._json_response(
                200,
                {
                    "object": "list",
                    "data": [
                        {"id": model, "object": "model", "created": now, "owned_by": "codex"}
                        for model in self.server.models
                    ],
                },
            )
            return
        if self.path.rstrip("/") == "":
            self._json_response(200, {"status": "ok", "models": self.server.models})
            return
        self._json_response(404, {"error": {"message": "Not found"}})

    def _sse_event(self, payload: Any) -> None:
        event_type = payload.get("type") if isinstance(payload, dict) else None
        if event_type:
            self.wfile.write(f"event: {event_type}\n".encode("utf-8"))
        self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _chat_completions(self, payload: dict[str, Any]) -> None:
        model = str(payload.get("model") or "coder")
        prompt = build_prompt(payload.get("messages") or [])
        if not prompt:
            raise ValueError("messages must contain text content")
        created = int(time.time())
        completion_id = f"chatcmpl-codex-{uuid.uuid4().hex}"
        request_id = completion_id
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self._sse_event(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
                }
            )
            progress_text: list[str] = []

            def send_progress(message: str) -> None:
                delta = f"[Codex] {message}\n"
                progress_text.append(delta)
                self._sse_event(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
                    }
                )

            try:
                text = run_codex(
                    prompt,
                    model=model,
                    timeout=self.server.codex_timeout,
                    workdir=self.server.workdir,
                    codex_command=self.server.codex_command,
                    use_windows_codex=self.server.use_windows_codex,
                    request_id=request_id,
                    progress_callback=send_progress,
                    progress_interval=self.server.progress_interval,
                )
            except Exception as exc:
                error_text = f"[Codex] Fehler: {exc}\n"
                self._sse_event(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": error_text}, "finish_reason": None}],
                    }
                )
                self._sse_event(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                )
                self.wfile.write(b"data: [DONE]\n\n")
                return

            for chunk in chunk_text(text):
                self._sse_event(
                    {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{"index": 0, "delta": {"content": chunk}, "finish_reason": None}],
                    }
                )
            self._sse_event(
                {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                }
            )
            self.wfile.write(b"data: [DONE]\n\n")
            return
        text = run_codex(
            prompt,
            model=model,
            timeout=self.server.codex_timeout,
            workdir=self.server.workdir,
            codex_command=self.server.codex_command,
            use_windows_codex=self.server.use_windows_codex,
            request_id=request_id,
            progress_interval=self.server.progress_interval,
        )
        self._json_response(200, chat_completion_response(completion_id, model, text, created))

    def _responses(self, payload: dict[str, Any]) -> None:
        model = str(payload.get("model") or "coder")
        prompt = build_prompt_from_responses(payload)
        if not prompt:
            raise ValueError("input must contain text content")
        created = int(time.time())
        response_id = f"resp_codex_{uuid.uuid4().hex}"
        message_id = f"msg_codex_{uuid.uuid4().hex}"
        request_id = response_id
        if payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            base_response = {
                "id": response_id,
                "object": "response",
                "created_at": created,
                "status": "in_progress",
                "model": model,
                "output": [],
            }
            self._sse_event({"type": "response.created", "response": base_response})
            self._sse_event({"type": "response.in_progress", "response": base_response})
            self._sse_event(
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": {
                        "id": message_id,
                        "type": "message",
                        "status": "in_progress",
                        "role": "assistant",
                        "content": [],
                    },
                }
            )
            self._sse_event(
                {
                    "type": "response.content_part.added",
                    "output_index": 0,
                    "content_index": 0,
                    "part": {"type": "output_text", "text": "", "annotations": []},
                }
            )
            progress_text: list[str] = []

            def send_progress(message: str) -> None:
                delta = f"[Codex] {message}\n"
                progress_text.append(delta)
                self._sse_event(
                    {
                        "type": "response.output_text.delta",
                        "output_index": 0,
                        "content_index": 0,
                        "delta": delta,
                    }
                )

            try:
                text = run_codex(
                    prompt,
                    model=model,
                    timeout=self.server.codex_timeout,
                    workdir=self.server.workdir,
                    codex_command=self.server.codex_command,
                    use_windows_codex=self.server.use_windows_codex,
                    request_id=request_id,
                    progress_callback=send_progress,
                    progress_interval=self.server.progress_interval,
                )
            except Exception as exc:
                error_text = f"[Codex] Fehler: {exc}\n"
                final_part = {"type": "output_text", "text": error_text, "annotations": []}
                final_item = responses_message_item(message_id, error_text)
                self._sse_event(
                    {
                        "type": "response.output_text.delta",
                        "output_index": 0,
                        "content_index": 0,
                        "delta": error_text,
                    }
                )
                self._sse_event(
                    {
                        "type": "response.output_text.done",
                        "output_index": 0,
                        "content_index": 0,
                        "text": error_text,
                    }
                )
                self._sse_event(
                    {
                        "type": "response.content_part.done",
                        "output_index": 0,
                        "content_index": 0,
                        "part": final_part,
                    }
                )
                self._sse_event({"type": "response.output_item.done", "output_index": 0, "item": final_item})
                self._sse_event(
                    {
                        "type": "response.failed",
                        "response": {
                            **responses_result(response_id, message_id, model, error_text, created),
                            "status": "failed",
                        },
                    }
                )
                self.wfile.write(b"data: [DONE]\n\n")
                return

            for chunk in chunk_text(text):
                self._sse_event(
                    {
                        "type": "response.output_text.delta",
                        "output_index": 0,
                        "content_index": 0,
                        "delta": chunk,
                    }
                )
            visible_text = "".join(progress_text) + text
            final_part = {"type": "output_text", "text": visible_text, "annotations": []}
            final_item = responses_message_item(message_id, visible_text)
            self._sse_event(
                {
                    "type": "response.output_text.done",
                    "output_index": 0,
                    "content_index": 0,
                    "text": visible_text,
                }
            )
            self._sse_event(
                {
                    "type": "response.content_part.done",
                    "output_index": 0,
                    "content_index": 0,
                    "part": final_part,
                }
            )
            self._sse_event({"type": "response.output_item.done", "output_index": 0, "item": final_item})
            self._sse_event(
                {
                    "type": "response.completed",
                    "response": responses_result(response_id, message_id, model, visible_text, created),
                }
            )
            self.wfile.write(b"data: [DONE]\n\n")
            return
        text = run_codex(
            prompt,
            model=model,
            timeout=self.server.codex_timeout,
            workdir=self.server.workdir,
            codex_command=self.server.codex_command,
            use_windows_codex=self.server.use_windows_codex,
            request_id=request_id,
            progress_interval=self.server.progress_interval,
        )
        self._json_response(200, responses_result(response_id, message_id, model, text, created))

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path not in {"/v1/chat/completions", "/chat/completions", "/v1/responses", "/responses"}:
            self._json_response(404, {"error": {"message": "Not found"}})
            return
        if not self._require_authorized():
            return

        try:
            payload = self._read_json()
            model = payload.get("model")
            request_id = f"req_{uuid.uuid4().hex}"
            log_event(
                "request.start",
                request_id=request_id,
                path=path,
                model=model,
                stream=bool(payload.get("stream")),
            )
            if path in {"/v1/responses", "/responses"}:
                self._responses(payload)
            else:
                self._chat_completions(payload)
            log_event("request.done", request_id=request_id, path=path)
        except Exception as exc:
            log_event("request.failed", path=path, error=str(exc))
            self._json_response(500, {"error": {"message": str(exc), "type": "codex_bridge_error"}})

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.verbose:
            super().log_message(format, *args)


class CodexBridgeServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        models: list[str],
        codex_timeout: int,
        workdir: Path,
        codex_command: str | None,
        use_windows_codex: bool,
        api_key: str | None,
        progress_interval: int,
        verbose: bool,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.models = models
        self.codex_timeout = codex_timeout
        self.workdir = workdir
        self.codex_command = codex_command
        self.use_windows_codex = use_windows_codex
        self.api_key = api_key
        self.progress_interval = progress_interval
        self.verbose = verbose


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expose local Codex CLI as a minimal OpenAI-compatible chat provider.")
    parser.add_argument("--host", default=os.getenv("CODEX_BRIDGE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("CODEX_BRIDGE_PORT", "4010")))
    parser.add_argument("--model", action="append", dest="models", help="Model id to expose. Can be passed multiple times.")
    parser.add_argument("--codex-timeout", type=int, default=int(os.getenv("CODEX_BRIDGE_TIMEOUT", "900")))
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=int(os.getenv("CODEX_BRIDGE_PROGRESS_INTERVAL", "15")),
        help="Seconds between visible streaming progress heartbeats.",
    )
    parser.add_argument("--codex-command", default=os.getenv("CODEX_BRIDGE_CODEX_COMMAND"))
    parser.add_argument("--windows-codex", action="store_true", default=is_truthy(os.getenv("CODEX_BRIDGE_WINDOWS_CODEX")))
    parser.add_argument(
        "--api-key",
        default=read_secret_value(os.getenv("CODEX_BRIDGE_API_KEY"), os.getenv("CODEX_BRIDGE_API_KEY_FILE")),
    )
    parser.add_argument("--workdir", default=os.getenv("CODEX_BRIDGE_WORKDIR", str(Path(__file__).resolve().parents[1])))
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = args.models or parse_model_list(os.getenv("CODEX_BRIDGE_MODELS")) or DEFAULT_MODELS
    server = CodexBridgeServer(
        (args.host, args.port),
        CodexBridgeHandler,
        models=models,
        codex_timeout=args.codex_timeout,
        workdir=Path(args.workdir).resolve(),
        codex_command=args.codex_command,
        use_windows_codex=args.windows_codex,
        api_key=args.api_key,
        progress_interval=args.progress_interval,
        verbose=args.verbose,
    )
    print(f"Codex OpenAI bridge listening on http://{args.host}:{args.port}/v1", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
