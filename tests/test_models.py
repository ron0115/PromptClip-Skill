import unittest

from video_highlight.models import ModelDecision, validate_model_decisions


class ModelValidationTests(unittest.TestCase):
    def test_accepts_decisions_with_known_window_ids(self):
        decisions = validate_model_decisions(
            [
                {
                    "window_id": "window-1",
                    "keep": True,
                    "score": 0.87,
                    "tags": ["clear"],
                    "reason": "The subject is visible and the action is complete.",
                }
            ],
            known_window_ids={"window-1"},
        )

        self.assertEqual(decisions, [
            ModelDecision("window-1", True, 0.87, ["clear"], "The subject is visible and the action is complete.")
        ])

    def test_rejects_unknown_window_and_invalid_score(self):
        with self.assertRaises(ValueError):
            validate_model_decisions(
                [{"window_id": "missing", "keep": True, "score": 1.2, "tags": [], "reason": "bad"}],
                known_window_ids={"window-1"},
            )


if __name__ == "__main__":
    unittest.main()
