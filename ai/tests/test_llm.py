"""LLM 서버 클라이언트: 실패는 None, 꺼짐 유지, 같은 질문 기억, 문서당 호출 상한."""
import socket
import threading
import time

from coa_ai.llm import LLMClient
from tests.llm_server import FakeLLMServer

SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}


def closed_port_url() -> str:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return f"http://127.0.0.1:{port}"


def test_json_chat_returns_parsed_dict():
    with FakeLLMServer(['{"name": "Na"}']) as srv:
        assert LLMClient(srv.url).json_chat("sys", "user", SCHEMA) == {"name": "Na"}
    body = srv.requests[0]
    assert body["temperature"] == 0
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_text_chat_returns_content():
    with FakeLLMServer(["제목: x\n\n본문"]) as srv:
        assert LLMClient(srv.url).text_chat("sys", "user") == "제목: x\n\n본문"
    assert "response_format" not in srv.requests[0]


def test_connection_refused_returns_none_and_marks_down():
    client = LLMClient(closed_port_url())
    assert client.json_chat("sys", "a", SCHEMA) is None
    t0 = time.perf_counter()
    assert client.json_chat("sys", "b", SCHEMA) is None
    assert time.perf_counter() - t0 < 0.5


def test_down_state_is_shared_with_document_view():
    client = LLMClient(closed_port_url())
    assert client.json_chat("sys", "a", SCHEMA) is None
    t0 = time.perf_counter()
    assert client.for_document().json_chat("sys", "b", SCHEMA) is None
    assert time.perf_counter() - t0 < 0.5


def test_timeout_returns_none():
    with FakeLLMServer([("sleep", 2)]) as srv:
        assert LLMClient(srv.url, timeout=0.5).json_chat("sys", "user", SCHEMA) is None


def test_http_error_returns_none():
    with FakeLLMServer([("status", 500)]) as srv:
        assert LLMClient(srv.url).json_chat("sys", "user", SCHEMA) is None


def test_garbage_json_is_none():
    with FakeLLMServer(["not json"]) as srv:
        assert LLMClient(srv.url).json_chat("sys", "user", SCHEMA) is None


def test_json_in_code_fence_is_read():
    with FakeLLMServer(['```json\n{"kind": "nd"}\n```']) as srv:
        assert LLMClient(srv.url).json_chat("sys", "user", SCHEMA) == {"kind": "nd"}


def test_same_question_is_cached():
    with FakeLLMServer(['{"name": "Na"}']) as srv:
        client = LLMClient(srv.url)
        assert client.json_chat("sys", "user", SCHEMA) == client.json_chat("sys", "user", SCHEMA)
        assert client.for_document().json_chat("sys", "user", SCHEMA) == {"name": "Na"}
    assert len(srv.requests) == 1


def test_document_call_limit():
    with FakeLLMServer(['{"name": "Na"}']) as srv:
        doc = LLMClient(srv.url).for_document(max_calls=2)
        assert doc.json_chat("sys", "a", SCHEMA) is not None
        assert doc.json_chat("sys", "a", SCHEMA) is not None  # 기억한 답은 상한에 세지 않음
        assert doc.json_chat("sys", "b", SCHEMA) is not None
        assert doc.json_chat("sys", "c", SCHEMA) is None
    assert len(srv.requests) == 2


def test_threads_share_cache_safely():
    with FakeLLMServer(['{"name": "Na"}']) as srv:
        client = LLMClient(srv.url)
        results, errors = [], []

        def ask():
            try:
                results.append(client.json_chat("sys", "same", SCHEMA))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=ask) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert errors == []
    assert results == [{"name": "Na"}] * 8
