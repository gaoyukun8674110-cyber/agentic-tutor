import unittest

from app.services.llm_service import LLMService


class MaterialContextPromptTests(unittest.TestCase):
    def test_system_prompt_formats_retrieved_material_context(self):
        service = LLMService()

        prompt = service._build_system_prompt(
            prompt_profile="three_stage",
            tutor_context={
                "learning_phase": "understanding",
                "material_context": {
                    "chunks": [
                        {
                            "filename": "probability-notes.txt",
                            "source_label": "probability-notes.txt chunk 1",
                            "content": "Bayes theorem connects prior, likelihood, and posterior.",
                            "score": 0.82,
                        }
                    ]
                },
            },
        )

        self.assertIn("probability-notes.txt chunk 1", prompt)
        self.assertIn("Bayes theorem connects prior", prompt)
        self.assertNotIn("{'chunks'", prompt)

    def test_system_prompt_marks_web_search_context(self):
        service = LLMService()

        prompt = service._build_system_prompt(
            prompt_profile="three_stage",
            tutor_context={
                "learning_phase": "understanding",
                "material_context": {
                    "chunks": [
                        {
                            "source_label": "Example",
                            "content": "Fresh web result.",
                            "url": "https://example.com",
                            "score": 0.8,
                            "origin": "web",
                        }
                    ]
                },
            },
        )

        self.assertIn("Live web search was performed for this turn", prompt)
        self.assertIn("https://example.com", prompt)


if __name__ == "__main__":
    unittest.main()
