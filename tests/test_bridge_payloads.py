import unittest

import io
import json
import tempfile
from types import SimpleNamespace
from pathlib import Path

from src.codex_openai_bridge import (
    CodexBridgeHandler,
    VisibleDelta,
    build_prompt_from_responses,
    codex_json_event_message,
    compress_output,
    describe_shell_command,
    final_text_was_streamed,
    format_visible_delta,
    map_codex_json_event,
    next_heartbeat_activity,
    parse_codex_json_line,
    parse_model_list,
    progress_delta,
    public_codex_log_line,
    redact_sensitive,
    read_secret_value,
    responses_result,
    responses_usage_from_codex,
)


class BridgePayloadTests(unittest.TestCase):
    def test_parse_model_list(self):
        self.assertEqual(parse_model_list("coder, gpt-5.5,,codex"), ["coder", "gpt-5.5", "codex"])
        self.assertIsNone(parse_model_list(""))

    def test_build_prompt_from_responses(self):
        payload = {
            "instructions": "Systemtext",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Aufgabe"}],
                }
            ],
        }
        self.assertEqual(build_prompt_from_responses(payload), "SYSTEM:\nSystemtext\n\nUSER:\nAufgabe")

    def test_build_prompt_from_responses_accepts_plain_message_items(self):
        payload = {
            "input": [
                {"role": "user", "content": [{"type": "input_text", "text": "Frage"}]},
                {"role": "assistant", "content": [{"type": "output_text", "text": "Zwischenantwort"}]},
                {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.invalid/a.png"}}]},
            ],
        }
        self.assertEqual(
            build_prompt_from_responses(payload),
            "USER:\nFrage\n\nASSISTANT:\nZwischenantwort\n\nUSER:\n[Bildinhalt]",
        )

    def test_responses_result_shape(self):
        result = responses_result("resp_1", "msg_1", "coder", "Hallo", 123)
        self.assertEqual(result["object"], "response")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["output"][0]["content"][0]["text"], "Hallo")

    def test_responses_result_uses_codex_usage(self):
        usage = responses_usage_from_codex(
            {
                "input_tokens": 10,
                "cached_input_tokens": 4,
                "output_tokens": 7,
                "reasoning_output_tokens": 3,
            }
        )
        result = responses_result("resp_1", "msg_1", "coder", "Hallo", 123, usage)
        self.assertEqual(result["usage"]["input_tokens"], 10)
        self.assertEqual(result["usage"]["output_tokens_details"]["reasoning_tokens"], 3)
        self.assertEqual(result["usage"]["input_tokens_details"]["cached_tokens"], 4)

    def test_read_secret_value_from_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "secret"
            path.write_text("abc123\n", encoding="utf-8")
            self.assertEqual(read_secret_value(None, str(path)), "abc123")
            self.assertEqual(read_secret_value("direct", str(path)), "direct")

    def test_public_codex_log_line_redacts_prompt_content(self):
        self.assertEqual(public_codex_log_line("stderr", "model: gpt-5.5"), "model: gpt-5.5")
        self.assertIsNone(public_codex_log_line("stderr", "USER:"))
        self.assertIsNone(public_codex_log_line("stderr", "vertraulicher prompt"))
        self.assertIsNone(public_codex_log_line("stdout", "final answer"))

    def test_codex_json_event_message(self):
        self.assertEqual(
            codex_json_event_message({"type": "turn.started"}),
            "Bearbeitung begonnen.",
        )
        self.assertEqual(
            codex_json_event_message(
                {
                    "type": "item.started",
                    "item": {"type": "command_execution", "command": "/bin/bash -lc ls"},
                }
            ),
            "Shell: listet das aktuelle Verzeichnis.",
        )
        self.assertIn(
            "Ausgabe:",
            codex_json_event_message(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": "/bin/bash -lc ls",
                        "aggregated_output": "a.txt\nb.txt\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            ),
        )
        self.assertEqual(
            codex_json_event_message({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}}),
            "OK",
        )

    def test_compress_output_omits_middle(self):
        output = "\n".join(f"line-{i}" for i in range(60))
        compressed = compress_output(output, max_lines=10)
        self.assertIn("Zeilen ausgelassen", compressed)
        self.assertIn("line-0", compressed)
        self.assertIn("line-59", compressed)

    def test_describe_shell_command(self):
        summary, done, policy = describe_shell_command(
            "/bin/bash -lc \"sed -n '1,220p' /home/codex/.codex/plugins/cache/skill/SKILL.md\""
        )
        self.assertIn("liest", summary)
        self.assertIn("Zeilen 1-220", summary)
        self.assertEqual(done, "Datei gelesen")
        self.assertEqual(policy, "suppress")

    def test_progress_delta_is_markdown(self):
        self.assertEqual(progress_delta("arbeitet."), "Codex: arbeitet.\n\n")

    def test_completed_steps_do_not_repeat_as_heartbeat_activity(self):
        self.assertEqual(
            next_heartbeat_activity("Shell abgeschlossen: Datei gelesen, Exit 0.\nErgebnis: 10 Zeilen gelesen."),
            "wertet die letzte Ausgabe aus und plant den nächsten Schritt",
        )

    def test_reasoning_does_not_expose_private_content(self):
        deltas = map_codex_json_event(
            {"type": "item.completed", "item": {"type": "reasoning", "text": "private chain of thought"}}
        )
        self.assertEqual(deltas[0].text, "Analyseabschnitt abgeschlossen.")
        self.assertNotIn("private", deltas[0].text)

    def test_agent_message_formats_as_assistant_text(self):
        delta = map_codex_json_event({"type": "item.completed", "item": {"type": "agent_message", "text": "Ich prüfe."}})[0]
        self.assertEqual(delta.kind, "agent")
        self.assertEqual(format_visible_delta(delta), "Ich prüfe.\n\n")

    def test_redacts_secret_like_values(self):
        redacted = redact_sensitive("Authorization: Bearer sk-testSecretToken123456789 OPENAI_API_KEY=abc123")
        self.assertIn("[REDACTED]", redacted)
        self.assertNotIn("sk-testSecretToken", redacted)
        self.assertNotIn("abc123", redacted)

    def test_bad_json_line_is_ignored(self):
        self.assertIsNone(parse_codex_json_line("{not-json"))
        self.assertEqual(parse_codex_json_line('{"type":"turn.started"}')["type"], "turn.started")

    def test_final_answer_duplicate_detection(self):
        self.assertTrue(final_text_was_streamed("Fertig.", ["Fertig."]))
        self.assertFalse(final_text_was_streamed("Fertig.", ["Zwischenstand."]))

    def test_sse_event_is_valid_json_and_terminated(self):
        fake = SimpleNamespace(wfile=io.BytesIO())
        CodexBridgeHandler._sse_event(fake, {"type": "response.output_text.delta", "delta": "Hallo"})
        raw = fake.wfile.getvalue().decode("utf-8")
        self.assertTrue(raw.endswith("\n\n"))
        self.assertIn("event: response.output_text.delta\n", raw)
        payload = json.loads(raw.split("data: ", 1)[1])
        self.assertEqual(payload["delta"], "Hallo")

    def test_chat_completions_fallback_exists_but_responses_is_documented_default(self):
        self.assertTrue(callable(CodexBridgeHandler._chat_completions))


if __name__ == "__main__":
    unittest.main()
