import unittest

from app.api.llm import _inject_material_context


class FakeMaterialService:
    def __init__(self, results=None):
        self.calls = []
        self.results = results or [
            {
                "material_id": 7,
                "source_label": "probability.txt chunk 1",
                "content": "Bayes theorem uses posterior probability.",
                "score": 0.91,
            }
        ]

    def search_materials(self, query, user_id=None, material_ids=None, top_k=None):
        self.calls.append(
            {
                "query": query,
                "user_id": user_id,
                "material_ids": material_ids,
                "top_k": top_k,
            }
        )
        return self.results


class LlmMaterialContextTests(unittest.TestCase):
    def test_inject_material_context_searches_selected_materials(self):
        service = FakeMaterialService()

        tutor_context, chunks = _inject_material_context(
            tutor_context={"learning_phase": "understanding", "material_ids": [7, "8", "bad", 0]},
            last_user_message="What is posterior probability?",
            material_service=service,
            user_id="learner-1",
            top_k=3,
        )

        self.assertEqual(service.calls[0]["query"], "What is posterior probability?")
        self.assertEqual(service.calls[0]["user_id"], "learner-1")
        self.assertEqual(service.calls[0]["material_ids"], [7, 8])
        self.assertEqual(service.calls[0]["top_k"], 3)
        self.assertEqual(tutor_context["material_context"]["chunks"], chunks)
        self.assertEqual(chunks[0]["source_label"], "probability.txt chunk 1")

    def test_inject_material_context_skips_empty_user_message(self):
        service = FakeMaterialService()

        tutor_context, chunks = _inject_material_context(
            tutor_context={"material_ids": [7]},
            last_user_message=None,
            material_service=service,
            user_id=None,
            top_k=3,
        )

        self.assertEqual(service.calls, [])
        self.assertNotIn("material_context", tutor_context)
        self.assertEqual(chunks, [])

    def test_inject_material_context_skips_when_material_ids_missing(self):
        service = FakeMaterialService()

        tutor_context, chunks = _inject_material_context(
            tutor_context={"learning_phase": "understanding"},
            last_user_message="What is an AI agent?",
            material_service=service,
            user_id="learner-1",
            top_k=3,
        )

        self.assertEqual(service.calls, [])
        self.assertNotIn("material_context", tutor_context)
        self.assertEqual(chunks, [])

    def test_inject_material_context_skips_empty_material_ids(self):
        service = FakeMaterialService()

        tutor_context, chunks = _inject_material_context(
            tutor_context={"material_ids": []},
            last_user_message="What is an AI agent?",
            material_service=service,
            user_id="learner-1",
            top_k=3,
        )

        self.assertEqual(service.calls, [])
        self.assertNotIn("material_context", tutor_context)
        self.assertEqual(chunks, [])

    def test_inject_material_context_filters_low_score_chunks(self):
        service = FakeMaterialService(
            results=[
                {
                    "material_id": 7,
                    "source_label": "grammar.txt chunk 1",
                    "content": "Unrelated grammar notes.",
                    "score": 0.1,
                }
            ]
        )

        tutor_context, chunks = _inject_material_context(
            tutor_context={"material_ids": [7]},
            last_user_message="What is an AI agent?",
            material_service=service,
            user_id="learner-1",
            top_k=3,
        )

        self.assertEqual(len(service.calls), 1)
        self.assertNotIn("material_context", tutor_context)
        self.assertEqual(chunks, [])


if __name__ == "__main__":
    unittest.main()
