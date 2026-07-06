import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services.chat_history import ChatHistoryService


class ChatHistoryServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def test_save_list_load_and_delete_conversation(self):
        db = self.SessionLocal()
        try:
            service = ChatHistoryService(db)

            summary = service.save_exchange(
                conversation_id=None,
                user_message="How do I solve linear equations?",
                assistant_message="Start by isolating the variable.",
                prompt_profile="socratic",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )

            self.assertEqual(summary["message_count"], 2)
            self.assertEqual(summary["title"], "Linear Equations")

            conversations = service.list_conversations(user_id="learner-1")
            self.assertEqual(len(conversations), 1)
            self.assertEqual(conversations[0]["id"], summary["id"])

            detail = service.get_conversation(summary["id"], user_id="learner-1")
            self.assertIsNotNone(detail)
            self.assertEqual(len(detail["messages"]), 2)
            self.assertEqual(detail["messages"][0]["role"], "user")
            self.assertEqual(detail["messages"][1]["role"], "assistant")

            self.assertTrue(service.delete_conversation(summary["id"], user_id="learner-1"))
            self.assertEqual(service.list_conversations(user_id="learner-1"), [])
        finally:
            db.close()

    def test_conversation_titles_are_concise_learning_topics(self):
        db = self.SessionLocal()
        try:
            service = ChatHistoryService(db)

            stats_summary = service.save_exchange(
                conversation_id=None,
                user_message="ok，我找了一份统计的教材，刚刚上传给你，我们接下来按照这个统计里面的内容进行学习！",
                assistant_message="我们先从统计推断的核心概念开始。",
                prompt_profile="three_stage",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )
            equation_summary = service.save_exchange(
                conversation_id=None,
                user_message="How do I solve linear equations?",
                assistant_message="Start by isolating the variable.",
                prompt_profile="socratic",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )

            self.assertEqual(stats_summary["title"], "统计教材学习")
            self.assertEqual(equation_summary["title"], "Linear Equations")
            self.assertLessEqual(len(stats_summary["title"]), 12)
        finally:
            db.close()

    def test_export_conversation_markdown_includes_metadata_summary_and_messages(self):
        db = self.SessionLocal()
        try:
            service = ChatHistoryService(db)
            summary = service.save_exchange(
                conversation_id=None,
                user_message="请解释置信区间",
                assistant_message="置信区间表示由抽样过程构造出的区间估计。",
                prompt_profile="three_stage",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )
            service.save_summary(
                conversation_id=summary["id"],
                content="学生正在学习统计推断里的置信区间。",
                source_message_count=2,
                user_id="learner-1",
            )

            exported = service.export_conversation_markdown(summary["id"], user_id="learner-1")

            self.assertIsNotNone(exported)
            self.assertEqual(exported["filename"], "置信区间训练.md")
            self.assertIn("# 置信区间训练", exported["content"])
            self.assertIn("学生正在学习统计推断里的置信区间。", exported["content"])
            self.assertIn("## User", exported["content"])
            self.assertIn("请解释置信区间", exported["content"])
            self.assertIn("## Tutor", exported["content"])
            self.assertIn("置信区间表示", exported["content"])
        finally:
            db.close()

    def test_compact_context_uses_summary_and_recent_messages_after_15_exchanges(self):
        db = self.SessionLocal()
        try:
            service = ChatHistoryService(db)
            conversation_id = None
            for index in range(15):
                summary = service.save_exchange(
                    conversation_id=conversation_id,
                    user_message=f"user question {index}",
                    assistant_message=f"assistant answer {index}",
                    prompt_profile="socratic",
                    provider="linkapi",
                    model="claude-haiku",
                    training_mode="focus",
                    user_id="learner-1",
                )
                conversation_id = summary["id"]

            service.save_summary(
                conversation_id=conversation_id,
                content="student is learning equations and needs guided hints",
                source_message_count=30,
                user_id="learner-1",
            )

            compact_messages = service.build_model_messages(
                conversation_id=conversation_id,
                pending_user_message="new question after summary",
                user_id="learner-1",
            )

            self.assertIsNotNone(compact_messages)
            self.assertIn("student is learning equations", compact_messages[0]["content"])
            self.assertEqual(compact_messages[-1]["content"], "new question after summary")
            self.assertEqual(len(compact_messages), 14)
        finally:
            db.close()

    def test_search_conversations_matches_messages_and_summaries(self):
        db = self.SessionLocal()
        try:
            service = ChatHistoryService(db)
            bayes = service.save_exchange(
                conversation_id=None,
                user_message="I need help with probability.",
                assistant_message="Bayes theorem connects prior and posterior probability.",
                prompt_profile="socratic",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )
            geometry = service.save_exchange(
                conversation_id=None,
                user_message="Explain triangle similarity.",
                assistant_message="Start by comparing corresponding angles.",
                prompt_profile="socratic",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )
            service.save_summary(
                conversation_id=geometry["id"],
                content="student is reviewing Euclidean geometry and angle chasing",
                source_message_count=2,
                user_id="learner-1",
            )

            message_results = service.search_conversations("posterior", user_id="learner-1")
            summary_results = service.search_conversations("euclidean", user_id="learner-1")
            unrelated_results = service.search_conversations("calculus", user_id="learner-1")

            self.assertEqual([item["id"] for item in message_results], [bayes["id"]])
            self.assertEqual([item["id"] for item in summary_results], [geometry["id"]])
            self.assertEqual(unrelated_results, [])
        finally:
            db.close()

    def test_user_scope_excludes_other_users_conversations(self):
        db = self.SessionLocal()
        try:
            service = ChatHistoryService(db)
            alice = service.save_exchange(
                conversation_id=None,
                user_message="alice statistics conversation",
                assistant_message="scoped to alice",
                prompt_profile="three_stage",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="alice",
            )
            other = service.save_exchange(
                conversation_id=None,
                user_message="private learner conversation",
                assistant_message="scoped to another learner",
                prompt_profile="three_stage",
                provider="linkapi",
                model="claude-haiku",
                training_mode="focus",
                user_id="learner-1",
            )

            alice_results = service.list_conversations(user_id="alice")
            learner_results = service.list_conversations(user_id="learner-1")

            self.assertEqual([item["id"] for item in alice_results], [alice["id"]])
            self.assertNotIn(other["id"], [item["id"] for item in alice_results])
            self.assertEqual([item["id"] for item in learner_results], [other["id"]])
            self.assertIsNotNone(service.get_conversation(alice["id"], user_id="alice"))
            self.assertIsNone(service.get_conversation(alice["id"], user_id="learner-1"))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
