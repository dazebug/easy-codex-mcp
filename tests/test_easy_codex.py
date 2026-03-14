import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from easy_codex.server import (
    continue_conversation,
    handle_codex_error,
    parse_codex_output,
    start_new_conversation,
)


class TestParseCodexOutput:
    """JSONL 파싱 함수 테스트"""

    def test_parse_normal_output(self):
        """정상적인 JSONL 출력을 파싱하는지 테스트 (item.text 형식)"""
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread_abc123"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "Hello, world!"},
                    }
                ),
            ]
        )
        result = parse_codex_output(output)
        assert result["thread_id"] == "thread_abc123"
        assert result["response"] == "Hello, world!"

    def test_parse_content_array_fallback(self):
        """content 배열 형식도 fallback으로 파싱하는지 테스트"""
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "content": [{"type": "text", "text": "Fallback response"}],
                },
            }
        )
        result = parse_codex_output(output)
        assert result["response"] == "Fallback response"

    def test_parse_empty_output(self):
        """빈 출력을 처리하는지 테스트"""
        result = parse_codex_output("")
        assert result["thread_id"] == ""
        assert result["response"] == ""

    def test_parse_partial_output_no_response(self):
        """thread.started만 있고 response가 없는 경우를 테스트"""
        output = json.dumps({"type": "thread.started", "thread_id": "thread_xyz"})
        result = parse_codex_output(output)
        assert result["thread_id"] == "thread_xyz"
        assert result["response"] == ""

    def test_parse_partial_output_no_thread(self):
        """thread_id 없이 response만 있는 경우를 테스트"""
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "Some response"},
            }
        )
        result = parse_codex_output(output)
        assert result["thread_id"] == ""
        assert result["response"] == "Some response"

    def test_parse_multiple_agent_messages_uses_last(self):
        """여러 agent_message가 있으면 마지막 것을 사용하는지 테스트"""
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread_001"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "First response"},
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "Last response"},
                    }
                ),
            ]
        )
        result = parse_codex_output(output)
        assert result["response"] == "Last response"

    def test_parse_ignores_non_agent_message_items(self):
        """agent_message가 아닌 item.completed는 무시하는지 테스트"""
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread_002"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "command_execution", "command": "ls", "exit_code": 0},
                    }
                ),
            ]
        )
        result = parse_codex_output(output)
        assert result["thread_id"] == "thread_002"
        assert result["response"] == ""

    def test_parse_invalid_json_lines_skipped(self):
        """잘못된 JSON 라인을 건너뛰는지 테스트"""
        output = "\n".join(
            [
                "not valid json",
                json.dumps({"type": "thread.started", "thread_id": "thread_ok"}),
                "{broken json",
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "valid response"},
                    }
                ),
            ]
        )
        result = parse_codex_output(output)
        assert result["thread_id"] == "thread_ok"
        assert result["response"] == "valid response"

    def test_parse_empty_text(self):
        """text가 빈 문자열인 경우를 테스트"""
        output = json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": ""},
            }
        )
        result = parse_codex_output(output)
        assert result["response"] == ""

    def test_parse_realistic_codex_output(self):
        """실제 codex CLI 출력과 유사한 전체 흐름을 테스트"""
        output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "019ca768-dcde-7840-a779-5e4daec5f381"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_0", "type": "agent_message", "text": "파일을 확인해볼게요."},
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "command_execution",
                            "command": "cat pyproject.toml",
                            "aggregated_output": '[project]\nname = "usuhari"',
                            "exit_code": 0,
                            "status": "completed",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "item_2", "type": "agent_message", "text": "프로젝트 이름은 `usuhari`입니다."},
                    }
                ),
                json.dumps({"type": "turn.completed", "usage": {"input_tokens": 100, "output_tokens": 50}}),
            ]
        )
        result = parse_codex_output(output)
        assert result["thread_id"] == "019ca768-dcde-7840-a779-5e4daec5f381"
        assert result["response"] == "프로젝트 이름은 `usuhari`입니다."


class TestHandleCodexError:
    """에러 처리 함수 테스트"""

    def test_command_not_found(self):
        """codex 미설치 에러를 감지하는지 테스트"""
        result = MagicMock()
        result.stderr = "codex: command not found"
        result.stdout = ""
        with pytest.raises(ToolError, match="codex CLI가 설치되어 있지 않습니다"):
            handle_codex_error(result)

    def test_auth_error(self):
        """인증 에러를 감지하는지 테스트"""
        result = MagicMock()
        result.stderr = "Error: Invalid API key provided"
        result.stdout = ""
        with pytest.raises(ToolError, match="인증에 실패했습니다"):
            handle_codex_error(result)

    def test_general_error(self):
        """일반 에러를 raise하는지 테스트"""
        result = MagicMock()
        result.stderr = "Some unexpected error"
        result.stdout = ""
        with pytest.raises(ToolError, match="Some unexpected error"):
            handle_codex_error(result)

    def test_error_from_stdout_when_stderr_empty(self):
        """stderr가 비어있으면 stdout에서 에러를 가져오는지 테스트"""
        result = MagicMock()
        result.stderr = ""
        result.stdout = "Error from stdout"
        with pytest.raises(ToolError, match="Error from stdout"):
            handle_codex_error(result)

    def test_unknown_error_when_both_empty(self):
        """둘 다 비어있으면 Unknown error를 raise하는지 테스트"""
        result = MagicMock()
        result.stderr = ""
        result.stdout = ""
        with pytest.raises(ToolError, match="Unknown error"):
            handle_codex_error(result)


class TestStartNewConversation:
    """start_new_conversation 함수 테스트"""

    @patch("easy_codex.server.subprocess.run")
    def test_successful_conversation(self, mock_run):
        """성공적인 대화 시작을 테스트"""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread_new"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "I can help with that."},
                    }
                ),
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = jsonl_output
        mock_run.return_value = mock_result

        result = start_new_conversation("Hello")
        assert result["thread_id"] == "thread_new"
        assert result["response"] == "I can help with that."

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["codex", "e", "--json", "Hello"]

    @patch("easy_codex.server.subprocess.run")
    def test_with_working_directory(self, mock_run):
        """working_directory 옵션이 올바르게 전달되는지 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"type": "thread.started", "thread_id": "t1"})
        mock_run.return_value = mock_result

        start_new_conversation("Fix bug", working_directory="/home/user/project")

        args = mock_run.call_args[0][0]
        assert args == ["codex", "e", "--json", "-C", "/home/user/project", "Fix bug"]

    @patch("easy_codex.server.subprocess.run")
    def test_codex_not_found_error(self, mock_run):
        """codex 미설치 에러를 처리하는지 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 127
        mock_result.stderr = "codex: command not found"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(ToolError, match="codex CLI가 설치되어 있지 않습니다"):
            start_new_conversation("Hello")

    @patch("easy_codex.server.subprocess.run")
    def test_timeout_error(self, mock_run):
        """타임아웃 에러를 처리하는지 테스트"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["codex"], timeout=300)

        with pytest.raises(ToolError, match="codex 실행 시간이 5분을 초과했습니다"):
            start_new_conversation("Long task")

    @patch("easy_codex.server.subprocess.run")
    def test_general_exception(self, mock_run):
        """일반 예외를 처리하는지 테스트"""
        mock_run.side_effect = OSError("No such file or directory")

        with pytest.raises(ToolError, match="No such file or directory"):
            start_new_conversation("Hello")


class TestContinueConversation:
    """continue_conversation 함수 테스트"""

    @patch("easy_codex.server.subprocess.run")
    def test_successful_resume(self, mock_run):
        """성공적인 대화 재개를 테스트"""
        jsonl_output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread_resumed"}),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "Continuing from where we left off."},
                    }
                ),
            ]
        )
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = jsonl_output
        mock_run.return_value = mock_result

        result = continue_conversation("thread_abc", "What next?")
        assert result["thread_id"] == "thread_resumed"
        assert result["response"] == "Continuing from where we left off."

        args = mock_run.call_args[0][0]
        assert args == ["codex", "e", "--json", "resume", "thread_abc", "What next?"]

    @patch("easy_codex.server.subprocess.run")
    def test_resume_with_working_directory(self, mock_run):
        """working_directory 옵션이 resume에서도 올바르게 전달되는지 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"type": "thread.started", "thread_id": "t1"})
        mock_run.return_value = mock_result

        continue_conversation("thread_abc", "Continue", working_directory="/tmp/work")

        args = mock_run.call_args[0][0]
        assert args == ["codex", "e", "--json", "resume", "thread_abc", "Continue"]
        assert mock_run.call_args[1]["cwd"] == "/tmp/work"

    @patch("easy_codex.server.subprocess.run")
    def test_resume_codex_error(self, mock_run):
        """resume 시 codex 에러를 처리하는지 테스트"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Thread not found"
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        with pytest.raises(ToolError, match="Thread not found"):
            continue_conversation("invalid_thread", "Hello")

    @patch("easy_codex.server.subprocess.run")
    def test_resume_timeout_error(self, mock_run):
        """resume 시 타임아웃 에러를 처리하는지 테스트"""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["codex"], timeout=300)

        with pytest.raises(ToolError, match="codex 실행 시간이 5분을 초과했습니다"):
            continue_conversation("thread_abc", "Long task")

    def test_empty_thread_id_error(self):
        """thread_id가 빈 문자열이면 에러를 raise하는지 테스트"""
        with pytest.raises(ToolError, match="thread_id는 필수 입력값입니다"):
            continue_conversation("", "Hello")

    def test_whitespace_thread_id_error(self):
        """thread_id가 공백만 있으면 에러를 raise하는지 테스트"""
        with pytest.raises(ToolError, match="thread_id는 필수 입력값입니다"):
            continue_conversation("   ", "Hello")
