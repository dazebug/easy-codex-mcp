import json
import subprocess

from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("EasyCodex")


def parse_codex_output(output: str) -> dict:
    """codex --json JSONL 출력을 파싱하여 thread_id와 response를 추출합니다.

    Args:
        output: codex CLI의 JSONL 출력 문자열

    Returns:
        {"thread_id": str, "response": str} 형태의 딕셔너리
    """
    thread_id = ""
    response = ""

    for line in output.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type", "")

        if event_type == "thread.started":
            thread_id = event.get("thread_id", "")

        elif event_type == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                # 마지막 agent_message의 text를 사용
                # codex CLI는 item.text에 직접 텍스트를 넣음
                text = item.get("text", "")
                if text:
                    response = text
                else:
                    # content 배열 형식도 fallback으로 지원
                    for part in item.get("content", []):
                        if part.get("type") == "text":
                            response = part.get("text", "")

    return {"thread_id": thread_id, "response": response}


def handle_codex_error(result: subprocess.CompletedProcess) -> None:
    """codex 명령 실행 에러를 처리하고 ToolError를 raise합니다.

    Args:
        result: subprocess.run()의 결과 객체

    Raises:
        ToolError: 사용자 친화적인 에러 메시지와 함께
    """
    stderr_output = result.stderr.strip()
    stdout_output = result.stdout.strip()
    error_output = stderr_output or stdout_output or "Unknown error"

    if "command not found" in error_output.lower() or "codex: not found" in error_output.lower():
        raise ToolError(
            "codex CLI가 설치되어 있지 않습니다. 'npm install -g @openai/codex' 명령으로 설치한 후 다시 시도하세요."
        )

    if "auth" in error_output.lower() or "api key" in error_output.lower():
        raise ToolError("codex 인증에 실패했습니다. OPENAI_API_KEY 환경 변수가 올바르게 설정되어 있는지 확인하세요.")

    raise ToolError(error_output)


@mcp.tool()
def start_new_conversation(prompt: str, working_directory: str | None = None) -> dict:
    """Start a new conversation with OpenAI Codex CLI.

    Runs codex CLI in read-only sandbox mode and returns a thread_id for continuing
    the conversation later.

    **Limitations:**
    - Runs in read-only sandbox — cannot modify files or execute shell commands.
    - Use only for read-only tasks: code reading, analysis, and Q&A.

    **When to use:**
    1. Analyzing the structure or behavior of a codebase
    2. Code review or root cause analysis of bugs
    3. Generating explanations or documentation drafts for code
    4. Getting refactoring or architecture suggestions


    Args:
        prompt: Prompt to send to codex. Use @filepath to mention files.
        working_directory: Directory path for codex to work in (optional).

    Returns:
        Dict with thread_id and response.
    """
    try:
        cmd = ["codex", "e", "--json"]
        if working_directory:
            cmd.extend(["-C", working_directory])
        cmd.append(prompt)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            handle_codex_error(result)

        return parse_codex_output(result.stdout)

    except subprocess.TimeoutExpired as e:
        raise ToolError("codex 실행 시간이 5분을 초과했습니다.") from e
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(str(e)) from e


@mcp.tool()
def continue_conversation(thread_id: str, prompt: str, working_directory: str | None = None) -> dict:
    """Continue an existing Codex conversation.

    Resumes a previous conversation using thread_id to maintain context.
    Same read-only sandbox limitations as start_new_conversation apply.

    **When to use:**
    1. Asking follow-up questions based on previous analysis
    2. Continuing multi-step analysis on the same codebase
    3. Sending additional requests while maintaining conversation context


    Args:
        thread_id: thread_id from a previous conversation.
        prompt: Follow-up prompt to send to codex. Use @filepath to mention files.
        working_directory: Directory path for codex to work in (optional).

    Returns:
        Dict with thread_id and response.
    """
    if not thread_id or not thread_id.strip():
        raise ToolError(
            "thread_id는 필수 입력값입니다. start_new_conversation으로 먼저 대화를 시작한 후, 반환된 thread_id를 사용하세요."
        )

    try:
        cmd = ["codex", "e", "--json", "resume", thread_id, prompt]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=working_directory,
        )

        if result.returncode != 0:
            handle_codex_error(result)

        return parse_codex_output(result.stdout)

    except subprocess.TimeoutExpired as e:
        raise ToolError("codex 실행 시간이 5분을 초과했습니다.") from e
    except ToolError:
        raise
    except Exception as e:
        raise ToolError(str(e)) from e


def main():
    mcp.run()


if __name__ == "__main__":
    main()
