#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import queue
import re
import select
import shlex
import signal
import shutil
import socket
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


class ClientDisconnected(Exception):
    pass


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


def compress_output(value: str, max_chars: int = 1800, max_lines: int = 40) -> str:
    clean = value.replace("\r", "").strip()
    if not clean:
        return ""
    lines = clean.splitlines()
    omitted_lines = max(0, len(lines) - max_lines)
    if omitted_lines:
        head_count = max_lines // 2
        tail_count = max_lines - head_count
        lines = lines[:head_count] + [f"... {omitted_lines} Zeilen ausgelassen ..."] + lines[-tail_count:]
    compact = "\n".join(lines)
    if len(compact) <= max_chars:
        return compact
    omitted_chars = len(compact) - max_chars
    head_count = max_chars // 2
    tail_count = max_chars - head_count
    return compact[:head_count].rstrip() + f"\n... {omitted_chars} Zeichen ausgelassen ...\n" + compact[-tail_count:].lstrip()


def output_stats(value: str) -> tuple[int, int]:
    clean = value.replace("\r", "").strip()
    if not clean:
        return 0, 0
    return len(clean.splitlines()), len(clean.encode("utf-8"))


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def command_output_block(value: str, policy: str = "auto") -> str:
    line_count, byte_count = output_stats(value)
    if policy == "suppress" and line_count:
        return (
            f"\nErgebnis: {line_count} Zeilen gelesen ({format_bytes(byte_count)}); "
            "Inhalt im Chat ausgeblendet, damit der Live-Status lesbar bleibt."
        )
    compact = compress_output(value)
    if not compact:
        return ""
    compact_lines = compact.splitlines()
    if len(compact_lines) <= 3 and len(compact) <= 260:
        return "\nAusgabe: " + " | ".join(line.strip() for line in compact_lines if line.strip())
    label = "Ausgabe"
    if line_count > len(compact_lines) or byte_count > len(compact.encode("utf-8")):
        label = f"Ausgabe gekürzt ({len(compact_lines)} von {line_count} Zeilen)"
    indented = "\n".join(f"  {line}" for line in compact_lines)
    return f"\n{label}:\n{indented}"


def strip_shell_wrapper(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError:
        return command.strip()
    if len(parts) >= 3 and parts[0] in {"/bin/bash", "bash", "/bin/sh", "sh"} and parts[1] in {"-lc", "-c"}:
        return parts[2].strip()
    return command.strip()


def compact_path(value: str, max_length: int = 90) -> str:
    path = value.strip().strip("'\"")
    if len(path) <= max_length:
        return path
    parts = re.split(r"([/\\])", path)
    if len(parts) >= 5:
        tail = "".join(parts[-5:])
        return f".../{tail}" if "/" in path else f"...\\{tail}"
    return "..." + path[-max_length + 3 :]


def describe_shell_command(command: str) -> tuple[str, str, str]:
    inner = strip_shell_wrapper(command)
    try:
        parts = shlex.split(inner)
    except ValueError:
        parts = []
    executable = Path(parts[0]).name if parts else ""

    sed_match = re.search(r"sed\s+-n\s+['\"]?([0-9]+),([0-9]+)p['\"]?\s+(.+)$", inner)
    if sed_match:
        start, end, path = sed_match.groups()
        return f"liest {compact_path(path)} (Zeilen {start}-{end})", "Datei gelesen", "suppress"

    if executable in {"rg", "ripgrep"}:
        query = next((part for part in parts[1:] if not part.startswith("-")), "")
        target = parts[-1] if len(parts) > 2 else ""
        if query and target and target != query:
            return f"sucht nach \"{sanitize_log_line(query, 80)}\" in {compact_path(target)}", "Suche abgeschlossen", "auto"
        if query:
            return f"sucht nach \"{sanitize_log_line(query, 80)}\"", "Suche abgeschlossen", "auto"
        return "sucht im Arbeitsbereich", "Suche abgeschlossen", "auto"

    if executable in {"cat", "type"} and len(parts) >= 2:
        return f"liest {compact_path(parts[-1])}", "Datei gelesen", "suppress"
    if executable in {"ls", "dir"}:
        target = compact_path(parts[-1]) if len(parts) >= 2 and not parts[-1].startswith("-") else "das aktuelle Verzeichnis"
        return f"listet {target}", "Verzeichnis gelesen", "auto"
    if executable in {"python", "python3"}:
        return "führt Python aus", "Python-Lauf abgeschlossen", "auto"
    if executable in {"node", "npm", "npx", "pnpm", "yarn"}:
        return f"führt {executable} aus", f"{executable}-Lauf abgeschlossen", "auto"
    if executable == "git":
        action = parts[1] if len(parts) > 1 else "Befehl"
        return f"prüft Git: {sanitize_log_line(action, 60)}", "Git-Schritt abgeschlossen", "auto"
    if executable == "docker":
        action = parts[1] if len(parts) > 1 else "Befehl"
        return f"nutzt Docker: {sanitize_log_line(action, 60)}", "Docker-Schritt abgeschlossen", "auto"

    return f"führt Shell-Schritt aus: {sanitize_log_line(inner, 180)}", "Shell-Schritt abgeschlossen", "auto"


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


def codex_json_event_message(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "")
    if event_type == "thread.started":
        thread_id = str(event.get("thread_id") or "")
        short_id = thread_id[-12:] if len(thread_id) > 12 else thread_id
        return f"Codex-Session {short_id} gestartet." if short_id else "Codex-Session gestartet."
    if event_type == "turn.started":
        return "Aufgabe angenommen; Codex analysiert den nächsten sinnvollen Schritt."
    if event_type == "turn.completed":
        usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        reasoning_tokens = usage.get("reasoning_output_tokens")
        if input_tokens is not None and output_tokens is not None:
            return (
                "Bearbeitung abgeschlossen; "
                f"Tokens: input {input_tokens}, output {output_tokens}, reasoning {reasoning_tokens or 0}."
            )
        return "Bearbeitung abgeschlossen."
    if event_type in {"turn.failed", "error"}:
        message = event.get("message") or event.get("error") or "unbekannter Fehler"
        return f"meldet einen Fehler: {sanitize_log_line(str(message), 300)}"

    item = event.get("item")
    if not isinstance(item, dict):
        return None

    item_type = str(item.get("type") or "")
    status = str(item.get("status") or "")
    if item_type == "reasoning":
        if event_type == "item.started":
            return "Denkt nach und plant den nächsten Schritt."
        return "Planungsschritt abgeschlossen."
    if item_type == "command_execution":
        raw_command = str(item.get("command") or "Shell-Befehl")
        summary, done_summary, output_policy = describe_shell_command(raw_command)
        if event_type == "item.started":
            return f"Startet: {summary}."
        exit_code = item.get("exit_code")
        output = command_output_block(str(item.get("aggregated_output") or ""), output_policy)
        if status == "failed" or (isinstance(exit_code, int) and exit_code != 0):
            return f"{done_summary} mit Fehler (Exit {exit_code}).{output}"
        return f"{done_summary} (Exit {exit_code}).{output}"

    if item_type in {"tool_call", "function_call"}:
        name = sanitize_log_line(str(item.get("name") or item.get("tool_name") or "Tool"), 160)
        if event_type == "item.started":
            return f"nutzt Tool {name}."
        if status:
            return f"Tool {name} ist {status}."
        return f"Tool {name} abgeschlossen."

    if item_type == "agent_message":
        return None

    if event_type == "item.started":
        return f"startet Schritt {item_type or 'unbekannt'}."
    if event_type == "item.completed" and item_type:
        return f"Schritt {item_type} abgeschlossen."
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


def stop_process(process: subprocess.Popen[str], request_id: str, reason: str) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name != "nt":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
    except ProcessLookupError:
        pass
    finally:
        log_event("codex.stopped", request_id=request_id, reason=reason)


def run_codex(
    prompt: str,
    model: str,
    timeout: int,
    workdir: Path,
    codex_command: str | None,
    use_windows_codex: bool,
    sandbox_mode: str,
    bypass_sandbox: bool,
    request_id: str,
    progress_callback: Callable[[str], None] | None = None,
    progress_interval: int = 15,
    disconnect_checker: Callable[[], bool] | None = None,
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
    process: subprocess.Popen[str] | None = None
    try:
        command = [
            *resolve_codex_command(codex_command, use_windows_codex),
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--cd",
            workdir_arg,
            "-m",
            target_model,
            "-o",
            output_arg,
            "-",
        ]
        if bypass_sandbox:
            command.insert(4, "--dangerously-bypass-approvals-and-sandbox")
        else:
            command[4:4] = ["--sandbox", sandbox_mode]
        command_label = " ".join(command[:2]) if len(command) > 1 else command[0]
        log_event(
            "codex.start",
            request_id=request_id,
            model=model,
            target_model=target_model,
            timeout_seconds=timeout,
            workdir=str(workdir),
            command=command_label,
            sandbox_mode="bypass" if bypass_sandbox else sandbox_mode,
            prompt_chars=len(prompt),
        )
        if progress_callback:
            progress_callback(f"Modell {target_model} gestartet; warte auf erste Codex-Aktivität.")

        process = subprocess.Popen(
            command,
            cwd=workdir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=os.name != "nt" and not use_windows_codex,
        )

        output_queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        stdout_tail: list[str] = []
        stderr_tail: list[str] = []

        def read_stream(stream_name: str, stream: Any) -> None:
            try:
                for line in stream:
                    output_queue.put((stream_name, line.rstrip("\r\n")))
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
        current_activity = "Codex initialisiert die Ausführung"

        while active_readers:
            now = time.monotonic()
            if disconnect_checker and not disconnect_checker():
                elapsed = int(now - started_at)
                if process.poll() is None:
                    stop_process(process, request_id, "client_disconnected")
                log_event("client.disconnected", request_id=request_id, elapsed_seconds=elapsed)
                raise ClientDisconnected()
            if process.poll() is None and now - started_at > timeout:
                elapsed = round(now - started_at, 1)
                stop_process(process, request_id, "timeout")
                log_event("codex.timeout", request_id=request_id, elapsed_seconds=elapsed)
                raise TimeoutError(f"codex exec timed out after {timeout} seconds")

            if progress_callback and now >= next_progress:
                elapsed = int(now - started_at)
                try:
                    progress_callback(f"arbeitet seit {elapsed}s weiter: {current_activity}.")
                except (BrokenPipeError, ConnectionResetError, OSError):
                    if process.poll() is None:
                        stop_process(process, request_id, "client_disconnected")
                    log_event("client.disconnected", request_id=request_id, elapsed_seconds=elapsed)
                    raise ClientDisconnected()
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
                stdout_tail = (stdout_tail + [sanitize_log_line(line)])[-20:]
            else:
                stderr_tail = (stderr_tail + [sanitize_log_line(line)])[-20:]

            if stream_name == "stdout":
                try:
                    codex_event = json.loads(line)
                except json.JSONDecodeError:
                    codex_event = None
                if isinstance(codex_event, dict):
                    event_type = str(codex_event.get("type") or "")
                    message = codex_json_event_message(codex_event)
                    message_preview = message.split("\n", 1)[0] if message else None
                    log_event(
                        "codex.event",
                        request_id=request_id,
                        codex_event=event_type,
                        message=sanitize_log_line(message_preview or "", 500) if message_preview else None,
                        visible_chars=len(message) if message else None,
                    )
                    if message and progress_callback:
                        current_activity = next_heartbeat_activity(message)
                        try:
                            progress_callback(message)
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            if process.poll() is None:
                                stop_process(process, request_id, "client_disconnected")
                            elapsed = int(time.monotonic() - started_at)
                            log_event("client.disconnected", request_id=request_id, elapsed_seconds=elapsed)
                            raise ClientDisconnected()
                    continue

            public_line = public_codex_log_line(stream_name, line)
            if public_line:
                log_event(
                    "codex.output",
                    request_id=request_id,
                    stream=stream_name,
                    line=sanitize_log_line(public_line),
                )
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
        if process is not None and process.poll() is None:
            stop_process(process, request_id, "cleanup")
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


def progress_delta(message: str) -> str:
    return f"Codex: {message}\n\n"


def next_heartbeat_activity(message: str) -> str:
    first_line = message.split("\n", 1)[0].rstrip(".")
    if any(
        marker in first_line
        for marker in (
            "abgeschlossen",
            "gelesen",
            "gelistet",
            "Bearbeitung abgeschlossen",
            "Planungsschritt abgeschlossen",
        )
    ):
        return "wertet die letzte Ausgabe aus und plant den nächsten Schritt"
    if first_line.startswith("Startet: "):
        return first_line.removeprefix("Startet: ")
    return first_line


class CodexBridgeHandler(BaseHTTPRequestHandler):
    server_version = "CodexOpenAIBridge/0.1"

    def _json_response(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            raise ClientDisconnected() from exc

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
        try:
            if event_type:
                self.wfile.write(f"event: {event_type}\n".encode("utf-8"))
            self.wfile.write(f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            raise ClientDisconnected() from exc

    def _write_done(self) -> None:
        try:
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError) as exc:
            raise ClientDisconnected() from exc

    def _client_connected(self) -> bool:
        try:
            readable, _, _ = select.select([self.connection], [], [], 0)
            if not readable:
                return True
            return bool(self.connection.recv(1, socket.MSG_PEEK))
        except BlockingIOError:
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

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
                delta = progress_delta(message)
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
                    sandbox_mode=self.server.sandbox_mode,
                    bypass_sandbox=self.server.bypass_sandbox,
                    request_id=request_id,
                    progress_callback=send_progress,
                    progress_interval=self.server.progress_interval,
                    disconnect_checker=self._client_connected,
                )
            except ClientDisconnected:
                raise
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
                self._write_done()
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
            self._write_done()
            return
        text = run_codex(
            prompt,
            model=model,
            timeout=self.server.codex_timeout,
            workdir=self.server.workdir,
            codex_command=self.server.codex_command,
            use_windows_codex=self.server.use_windows_codex,
            sandbox_mode=self.server.sandbox_mode,
            bypass_sandbox=self.server.bypass_sandbox,
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
                delta = progress_delta(message)
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
                    sandbox_mode=self.server.sandbox_mode,
                    bypass_sandbox=self.server.bypass_sandbox,
                    request_id=request_id,
                    progress_callback=send_progress,
                    progress_interval=self.server.progress_interval,
                    disconnect_checker=self._client_connected,
                )
            except ClientDisconnected:
                raise
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
                self._write_done()
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
            self._write_done()
            return
        text = run_codex(
            prompt,
            model=model,
            timeout=self.server.codex_timeout,
            workdir=self.server.workdir,
            codex_command=self.server.codex_command,
            use_windows_codex=self.server.use_windows_codex,
            sandbox_mode=self.server.sandbox_mode,
            bypass_sandbox=self.server.bypass_sandbox,
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
        except ClientDisconnected:
            log_event("request.client_disconnected", path=path)
            return
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
        sandbox_mode: str,
        bypass_sandbox: bool,
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
        self.sandbox_mode = sandbox_mode
        self.bypass_sandbox = bypass_sandbox
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
    parser.add_argument("--sandbox-mode", default=os.getenv("CODEX_BRIDGE_SANDBOX_MODE", "read-only"))
    parser.add_argument(
        "--bypass-sandbox",
        action="store_true",
        default=is_truthy(os.getenv("CODEX_BRIDGE_BYPASS_SANDBOX")),
        help="Run Codex without its own sandbox. Intended only when the bridge container is the sandbox boundary.",
    )
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
        sandbox_mode=args.sandbox_mode,
        bypass_sandbox=args.bypass_sandbox,
        api_key=args.api_key,
        progress_interval=args.progress_interval,
        verbose=args.verbose,
    )
    print(f"Codex OpenAI bridge listening on http://{args.host}:{args.port}/v1", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
