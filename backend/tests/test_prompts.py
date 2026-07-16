"""Tests for the prompt templates in ai_service.engine.prompts."""

import sys
from pathlib import Path

# Ensure ai_service is importable
_AI_SERVICE = Path(__file__).resolve().parents[2] / "ai_service"
sys.path.insert(0, str(_AI_SERVICE))

from engine import prompts


# ---------------------------------------------------------------------------
# System-prompt content checks
# ---------------------------------------------------------------------------


def test_prompt_contains_citation_instruction():
    """The system prompt must instruct the model to use [Sx] citation format."""
    sp = prompts.SYSTEM_PROMPT
    assert "[S" in sp, "System prompt should mention [Sx] citation format"
    assert "引用" in sp or "标注" in sp or "引用来源" in sp, (
        "System prompt should mention citations"
    )


def test_prompt_contains_rejection_instruction():
    """System prompt must instruct the model to reject when info is insufficient."""
    sp = prompts.SYSTEM_PROMPT
    assert "暂未找到相关信息" in sp or "未找到相关信息" in sp or "不足以" in sp, (
        "System prompt should instruct the model to reject unknown queries"
    )


def test_prompt_contains_disclaimer():
    """System prompt must include a timeliness / knowledge-boundary disclaimer."""
    sp = prompts.SYSTEM_PROMPT
    # Look for timeliness or date-awareness keywords
    assert any(kw in sp for kw in ("时间", "日期", "时效", "截止", "发布", "更新")), (
        "System prompt should mention timeliness or knowledge cutoff"
    )


def test_prompt_contains_reference_instruction():
    """System prompt must instruct the model to answer only from references."""
    sp = prompts.SYSTEM_PROMPT
    assert "参考资料" in sp or "参考" in sp or "提供" in sp, (
        "System prompt should instruct the model to base answers on provided references"
    )


def test_prompt_contains_anti_injection_guard():
    """System prompt must include an anti-prompt-injection guard."""
    sp = prompts.SYSTEM_PROMPT
    assert any(
        kw in sp
        for kw in (
            "忽略",
            "无视",
            "不要执行",
            "角色扮演",
            "ignore",
            "instructions in",
        )
    ), "System prompt should guard against prompt injection in references"


# ---------------------------------------------------------------------------
# build_context & build_prompt
# ---------------------------------------------------------------------------


def test_build_context_empty():
    assert prompts.build_context([]) == ""


def test_build_context_single_chunk():
    chunks = [{"content": "河海大学成立于1915年", "title": "学校简介"}]
    result = prompts.build_context(chunks)
    assert "河海大学成立于1915年" in result
    assert "来源" in result


def test_build_context_multiple_chunks():
    chunks = [
        {"content": "河海大学校训", "title": "校园文化"},
        {"content": "河海大学校区", "title": "校区概况"},
    ]
    result = prompts.build_context(chunks)
    assert "[S1]" in result
    assert "[S2]" in result


def test_build_prompt_returns_pair():
    """build_prompt must return a (system, user) tuple."""
    chunks = [{"content": "test", "title": "t"}]
    system, user = prompts.build_prompt("河海大学有几个校区？", chunks)
    assert isinstance(system, str)
    assert isinstance(user, str)
    assert len(system) > 0
    assert len(user) > 0


def test_build_prompt_includes_context_and_question():
    chunks = [{"content": "河海大学有三个校区", "title": "校区概况"}]
    _, user = prompts.build_prompt("有几个校区？", chunks)
    assert "河海大学有三个校区" in user
    assert "有几个校区" in user


# ---------------------------------------------------------------------------
# format_answer
# ---------------------------------------------------------------------------


def test_format_answer_structure():
    chunks = [{"content": "abc", "title": "t", "score": 0.9}]
    result = prompts.format_answer("答案", chunks)
    assert "answer" in result
    assert "sources" in result
    assert result["answer"] == "答案"
    assert len(result["sources"]) == 1


def test_format_answer_source_preview_truncated():
    long_content = "x" * 200
    chunks = [{"content": long_content, "title": "t", "score": 0.5}]
    result = prompts.format_answer("answer", chunks)
    preview = result["sources"][0]["content_preview"]
    assert len(preview) <= 100
