import unittest
from unittest import mock

import draft_machine


class DraftMachineCompatibilityTests(unittest.TestCase):
    def test_generate_content_supports_legacy_and_new_sdk_shapes(self):
        class FakeResponse:
            text = "draft body"

        class FakeLegacyModel:
            def __init__(self, *args, **kwargs):
                pass

            def generate_content(self, *args, **kwargs):
                return FakeResponse()

        class FakeLegacyModule:
            GenerativeModel = FakeLegacyModel

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            @property
            def models(self):
                return self

            def generate_content(self, *args, **kwargs):
                return FakeResponse()

        class FakeModernModule:
            Client = FakeClient

        with mock.patch.object(draft_machine, "genai", FakeLegacyModule):
            self.assertEqual(
                draft_machine._generate_content_with_gemini("system", "user", "fake-key"),
                "draft body",
            )

        with mock.patch.object(draft_machine, "genai", FakeModernModule):
            self.assertEqual(
                draft_machine._generate_content_with_gemini("system", "user", "fake-key"),
                "draft body",
            )


if __name__ == "__main__":
    unittest.main()
