import unittest

from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_current_user
from app.utils.errors import http_exception_handler, unhandled_exception_handler


class ErrorLocalizationTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_exception_handler(Exception, unhandled_exception_handler)
        app.add_exception_handler(StarletteHTTPException, http_exception_handler)

        @app.get("/protected")
        def protected(_current_user: str = Depends(get_current_user)):
            return {"ok": True}

        @app.get("/question")
        def question():
            raise HTTPException(status_code=404, detail="Question not found")

        @app.get("/provider")
        def provider():
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "llm_provider_error",
                    "user_message": "Model provider is temporarily unavailable",
                    "trace_id": "trace-1",
                },
            )

        self.client = TestClient(app)

    def test_missing_api_key_is_localized_for_zh_requests(self):
        response = self.client.get("/protected", headers={"Accept-Language": "zh-CN"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"]["user_message"], "缺少访问令牌")

    def test_plain_http_exception_messages_are_localized_for_zh_requests(self):
        response = self.client.get("/question", headers={"Accept-Language": "zh-CN"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["user_message"], "题目不存在")

    def test_public_error_payloads_are_localized_for_zh_requests(self):
        response = self.client.get("/provider", headers={"Accept-Language": "zh-CN"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"]["user_message"], "模型服务暂时不可用")


if __name__ == "__main__":
    unittest.main()
