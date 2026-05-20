import unittest

from src.codex_openai_bridge import build_prompt_from_responses, parse_model_list, responses_result


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


if __name__ == "__main__":
    unittest.main()
