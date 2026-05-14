"""Persistence helpers for Tutor chat conversations."""
from datetime import datetime
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.chat_history import TutorConversation, TutorConversationDigest, TutorConversationMessage


SUGGEST_NEW_CHAT_EXCHANGE_COUNT = 10
SUMMARY_EXCHANGE_COUNT = 15
RECENT_CONTEXT_EXCHANGES = 6


TITLE_RULES = [
    (("置信区间", "confidence interval"), "置信区间训练"),
    (("bootstrap", "自助法"), "Bootstrap训练"),
    (("线性回归", "least squares", "linear regression"), "线性回归训练"),
    (("假设检验", "显著性检验", "p-value", "p 值", "nhst"), "假设检验训练"),
    (("贝叶斯", "bayes", "bayesian", "posterior", "prior"), "贝叶斯推断"),
    (("概率统计",), "概率统计学习"),
    (("统计",), "统计学习"),
    (("概率", "probability"), "概率学习"),
    (("linear equation", "linear equations"), "Linear Equations"),
]

FILLER_TITLE_PREFIXES = [
    "ok",
    "好的",
    "接着",
    "继续",
    "我们",
    "请",
    "帮我",
    "我想",
]


class ChatHistoryService:
    """Store and retrieve Tutor chat conversations."""

    def __init__(self, db: Session):
        self.db = db

    def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = self.db.query(TutorConversation)
        if user_id:
            query = query.filter(self._user_scope_filter(user_id))

        conversations = (
            query.order_by(TutorConversation.updated_at.desc())
            .limit(max(1, min(limit, 100)))
            .all()
        )
        return [self._conversation_summary(conversation) for conversation in conversations]

    def search_conversations(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        cleaned_query = " ".join((query or "").split())
        if not cleaned_query:
            return self.list_conversations(user_id=user_id, limit=limit)

        pattern = f"%{cleaned_query.lower()}%"
        conversation_query = (
            self.db.query(TutorConversation)
            .outerjoin(TutorConversationMessage)
            .outerjoin(
                TutorConversationDigest,
                TutorConversationDigest.conversation_id == TutorConversation.id,
            )
        )
        if user_id:
            conversation_query = conversation_query.filter(self._user_scope_filter(user_id))

        conversation_query = conversation_query.filter(
            or_(
                func.lower(TutorConversation.title).like(pattern),
                func.lower(TutorConversation.training_mode).like(pattern),
                func.lower(TutorConversationMessage.content).like(pattern),
                func.lower(TutorConversationDigest.content).like(pattern),
            )
        ).order_by(TutorConversation.updated_at.desc())

        max_results = max(1, min(limit, 100))
        seen_ids = set()
        results: List[Dict[str, Any]] = []
        for conversation in conversation_query.all():
            if conversation.id in seen_ids:
                continue
            seen_ids.add(conversation.id)
            results.append(self._conversation_summary(conversation))
            if len(results) >= max_results:
                break
        return results

    def get_conversation(
        self,
        conversation_id: int,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        conversation = self._get_conversation_model(conversation_id, user_id)
        if not conversation:
            return None

        payload = self._conversation_summary(conversation)
        digest = self._get_digest_model(conversation.id)
        payload["summary"] = digest.content if digest else None
        payload["messages"] = [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "label": message.label,
                "created_at": message.created_at,
            }
            for message in conversation.messages
        ]
        return payload

    def export_conversation_markdown(
        self,
        conversation_id: int,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        conversation = self.get_conversation(conversation_id, user_id=user_id)
        if not conversation:
            return None

        exported_at = datetime.now().isoformat(timespec="seconds")
        lines = [
            f"# {conversation['title']}",
            "",
            f"- 导出时间：{exported_at}",
            f"- 会话创建：{conversation['created_at']}",
            f"- 最近更新：{conversation['updated_at']}",
            f"- 消息数量：{conversation['message_count']}",
        ]
        if conversation.get("summary"):
            lines.extend(["", "## 会话摘要", "", conversation["summary"].strip()])

        lines.extend(["", "## 对话记录"])
        for message in conversation.get("messages", []):
            role = message.get("role")
            label = "User" if role == "user" else (message.get("label") or "Tutor")
            created_at = message.get("created_at")
            heading = f"## {label}"
            if created_at:
                heading = f"{heading} · {created_at}"
            lines.extend(["", heading, "", (message.get("content") or "").strip()])

        title = self._safe_export_filename(conversation["title"])
        return {
            "filename": f"{title}.md",
            "content": "\n".join(lines).strip() + "\n",
        }

    def build_model_messages(
        self,
        conversation_id: int,
        pending_user_message: str,
        user_id: Optional[str] = None,
    ) -> Optional[List[Dict[str, str]]]:
        conversation = self._get_conversation_model(conversation_id, user_id)
        if not conversation:
            return None

        digest = self._get_digest_model(conversation.id)
        next_exchange_count = self.exchange_count(conversation.message_count) + 1
        if next_exchange_count <= SUMMARY_EXCHANGE_COUNT or not digest:
            return None

        compact_messages: List[Dict[str, str]] = [
            {
                "role": "user",
                "content": (
                    "以下是本学习会话的压缩摘要。请把它当作之前上下文，不要向学生暴露这是系统压缩内容。\n"
                    f"{digest.content}"
                ),
            }
        ]
        recent_messages = conversation.messages[-RECENT_CONTEXT_EXCHANGES * 2 :]
        compact_messages.extend(
            {"role": message.role, "content": message.content}
            for message in recent_messages
            if message.role in {"user", "assistant"}
        )
        compact_messages.append({"role": "user", "content": pending_user_message})
        return compact_messages

    def save_summary(
        self,
        conversation_id: int,
        content: str,
        source_message_count: int,
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        conversation = self._get_conversation_model(conversation_id, user_id)
        if not conversation:
            raise ValueError("Conversation not found")

        now = datetime.now().isoformat()
        digest = self._get_digest_model(conversation_id)
        if digest is None:
            digest = TutorConversationDigest(
                conversation_id=conversation_id,
                content=content,
                source_message_count=source_message_count,
                created_at=now,
                updated_at=now,
            )
            self.db.add(digest)
        else:
            digest.content = content
            digest.source_message_count = source_message_count
            digest.updated_at = now

        self.db.commit()
        return self._conversation_summary(conversation)

    def needs_summary(self, conversation_id: int, source_message_count: int) -> bool:
        if self.exchange_count(source_message_count) < SUMMARY_EXCHANGE_COUNT:
            return False
        digest = self._get_digest_model(conversation_id)
        return digest is None or digest.source_message_count < source_message_count

    def build_fallback_summary(self, messages: List[Dict[str, Any]]) -> str:
        user_messages = [message["content"] for message in messages if message.get("role") == "user"]
        assistant_messages = [message["content"] for message in messages if message.get("role") == "assistant"]
        latest_user = user_messages[-1] if user_messages else ""
        latest_assistant = assistant_messages[-1] if assistant_messages else ""
        return (
            f"本次学习会话已有 {len(user_messages)} 轮互动。\n"
            f"学生最近的问题：{latest_user[:240]}\n"
            f"Tutor 最近的引导：{latest_assistant[:240]}\n"
            "后续新会话应延续当前学习目标，优先保留学生已暴露出的卡点、需要复习的概念和下一步学习安排。"
        )

    @staticmethod
    def exchange_count(message_count: int) -> int:
        return message_count // 2

    def delete_conversation(
        self,
        conversation_id: int,
        user_id: Optional[str] = None,
    ) -> bool:
        conversation = self._get_conversation_model(conversation_id, user_id)
        if not conversation:
            return False

        self.db.delete(conversation)
        self.db.commit()
        return True

    def save_exchange(
        self,
        conversation_id: Optional[int],
        user_message: str,
        assistant_message: str,
        prompt_profile: str,
        provider: str,
        model: str,
        training_mode: Optional[str],
        user_id: Optional[str] = None,
        assistant_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        conversation = None
        if conversation_id is not None:
            conversation = self._get_conversation_model(conversation_id, user_id)
            if not conversation:
                raise ValueError("Conversation not found")

        if conversation is None:
            conversation = TutorConversation(
                user_id=user_id,
                title=self._title_from_message(user_message),
                training_mode=training_mode,
                prompt_profile=prompt_profile,
                provider=provider,
                model=model,
                message_count=0,
                created_at=now,
                updated_at=now,
            )
            self.db.add(conversation)
            self.db.flush()

        next_sequence = conversation.message_count
        self.db.add(
            TutorConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content=user_message,
                label=None,
                sequence=next_sequence,
                created_at=now,
            )
        )
        self.db.add(
            TutorConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=assistant_message,
                label=assistant_label or "Tutor",
                sequence=next_sequence + 1,
                created_at=now,
            )
        )

        conversation.training_mode = training_mode or conversation.training_mode
        conversation.prompt_profile = prompt_profile
        conversation.provider = provider
        conversation.model = model
        conversation.message_count = next_sequence + 2
        conversation.updated_at = now
        self.db.commit()
        self.db.refresh(conversation)
        return self._conversation_summary(conversation)

    def _get_conversation_model(
        self,
        conversation_id: int,
        user_id: Optional[str],
    ) -> Optional[TutorConversation]:
        query = self.db.query(TutorConversation).filter(TutorConversation.id == conversation_id)
        if user_id:
            query = query.filter(self._user_scope_filter(user_id))
        return query.first()

    @staticmethod
    def _user_scope_filter(user_id: str):
        return TutorConversation.user_id == user_id

    def _conversation_summary(self, conversation: TutorConversation) -> Dict[str, Any]:
        preview = ""
        if conversation.messages:
            preview = conversation.messages[-1].content[:90]

        return {
            "id": conversation.id,
            "title": conversation.title,
            "preview": preview,
            "training_mode": conversation.training_mode,
            "prompt_profile": conversation.prompt_profile,
            "provider": conversation.provider,
            "model": conversation.model,
            "message_count": conversation.message_count,
            "exchange_count": self.exchange_count(conversation.message_count),
            "should_suggest_new_chat": self.exchange_count(conversation.message_count) >= SUGGEST_NEW_CHAT_EXCHANGE_COUNT,
            "should_start_new_chat": self.exchange_count(conversation.message_count) >= SUMMARY_EXCHANGE_COUNT,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
        }

    def _get_digest_model(self, conversation_id: int) -> Optional[TutorConversationDigest]:
        return (
            self.db.query(TutorConversationDigest)
            .filter(TutorConversationDigest.conversation_id == conversation_id)
            .first()
        )

    def _title_from_message(self, content: str) -> str:
        normalized = " ".join((content or "").strip().split())
        if not normalized:
            return "Untitled study chat"

        lowered = normalized.lower()
        if "统计" in normalized and "教材" in normalized:
            return "统计教材学习"
        for keywords, title in TITLE_RULES:
            if any(keyword.lower() in lowered for keyword in keywords):
                return title

        title = self._fallback_compact_title(normalized)
        return title or "Untitled study chat"

    @staticmethod
    def _fallback_compact_title(content: str) -> str:
        title = re.split(r"[。！？!?;\n\r]", content, maxsplit=1)[0]
        title = re.sub(r"^[\s,，:：]+", "", title)
        for prefix in FILLER_TITLE_PREFIXES:
            pattern = re.compile(rf"^{re.escape(prefix)}[\s,，:：]*", re.IGNORECASE)
            title = pattern.sub("", title)
        title = title.strip(" -_，,。.!！?？:：")
        if not title:
            return ""

        if re.search(r"[\u4e00-\u9fff]", title):
            return title[:12] + ("..." if len(title) > 12 else "")
        words = re.findall(r"[A-Za-z0-9']+", title)
        if words:
            compact = " ".join(words[:4]).title()
            return compact[:32] + ("..." if len(compact) > 32 else "")
        return title[:24] + ("..." if len(title) > 24 else "")

    @staticmethod
    def _safe_export_filename(title: str) -> str:
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", title).strip(" ._")
        return safe or "tutor-conversation"
