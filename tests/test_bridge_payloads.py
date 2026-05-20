import unittest

import tempfile
from pathlib import Path

from src.codex_openai_bridge import (
    build_prompt_from_responses,
    codex_json_event_message,
    compress_output,
    describe_shell_command,
    next_heartbeat_activity,
    parse_model_list,
    progress_delta,
    public_codex_log_line,
    read_secret_value,
    responses_result,
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

    def test_responses_result_shape(self):
        result = responses_result("resp_1", "msg_1", "coder", "Hallo", 123)
        self.assertEqual(result["object"], "response")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["output"][0]["content"][0]["text"], "Hallo")

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
            "Aufgabe angenommen; Codex analysiert den nächsten sinnvollen Schritt.",
        )
        self.assertEqual(
            codex_json_event_message(
                {
                    "type": "item.started",
                    "item": {"type": "command_execution", "command": "/bin/bash -lc ls"},
                }
            ),
            "Startet: listet das aktuelle Verzeichnis.",
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
        self.assertIsNone(
            codex_json_event_message({"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}})
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
            next_heartbeat_activity("Datei gelesen (Exit 0).\nErgebnis: 10 Zeilen gelesen."),
            "wertet die letzte Ausgabe aus und plant den nächsten Schritt",
        )


if __name__ == "__main__":
    unittest.main()
