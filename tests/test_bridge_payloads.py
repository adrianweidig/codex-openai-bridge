import unittest

import tempfile
from pathlib import Path

from src.codex_openai_bridge import (
    build_prompt_from_responses,
    parse_model_list,
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


if __name__ == "__main__":
    unittest.main()
