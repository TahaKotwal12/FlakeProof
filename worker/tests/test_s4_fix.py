"""Unit tests for the pure patch-gate logic in flakeproof.stages.s4_fix:
unified diff parsing and static_precheck's rejection rules (sleep-based
fixes, deleted assertions, non-test files, oversized diffs, skip/xfail/rerun
decorators) -- no sandbox or LLM needed.
"""

from __future__ import annotations

from flakeproof.stages import s4_fix


def _diff(path: str, hunk_lines: list[str]) -> str:
    """Build a minimal unified diff with one file and one hunk."""
    header = f"--- a/{path}\n+++ b/{path}\n@@ -1,3 +1,3 @@\n"
    return header + "\n".join(hunk_lines) + "\n"


def test_parse_unified_diff_splits_added_and_removed_per_hunk() -> None:
    patch = _diff(
        "tests/test_api.py",
        [
            " import pytest",
            "-    time.sleep(1)",
            "+    freeze_time()",
            " def test_retry():",
        ],
    )
    hunks = s4_fix.parse_unified_diff(patch)
    assert len(hunks) == 1
    assert hunks[0].path == "tests/test_api.py"
    assert hunks[0].removed_lines == ["    time.sleep(1)"]
    assert hunks[0].added_lines == ["    freeze_time()"]


def test_static_precheck_approves_a_clean_test_only_patch() -> None:
    patch = _diff(
        "tests/test_api.py",
        [
            " import pytest",
            "+@pytest.fixture(autouse=True)",
            "+def reset_state():",
            "+    _state.clear()",
            "+    yield",
            "+    _state.clear()",
            " def test_retry():",
            "     assert retry_count() == 2",
        ],
    )
    assert s4_fix.static_precheck(patch) == []


def test_static_precheck_rejects_sleep_based_fix() -> None:
    patch = _diff("tests/test_api.py", [" def test_retry():", "+    time.sleep(5)", "     assert True"])
    objections = s4_fix.static_precheck(patch)
    assert any("sleep" in o.lower() for o in objections)


def test_static_precheck_rejects_asyncio_sleep_too() -> None:
    patch = _diff("tests/test_api.py", [" async def test_retry():", "+    await asyncio.sleep(2)"])
    objections = s4_fix.static_precheck(patch)
    assert any("sleep" in o.lower() for o in objections)


def test_static_precheck_rejects_deleted_assertion() -> None:
    patch = _diff(
        "tests/test_api.py",
        [
            " def test_retry():",
            "-    assert retry_count() == 2",
            "-    assert called",
            "+    assert retry_count() == 2",
        ],
    )
    objections = s4_fix.static_precheck(patch)
    assert any("assertion" in o.lower() for o in objections)


def test_static_precheck_allows_equal_assertion_swap() -> None:
    patch = _diff(
        "tests/test_api.py",
        [" def test_retry():", "-    assert x == 1", "+    assert x == 2"],
    )
    assert s4_fix.static_precheck(patch) == []


def test_static_precheck_rejects_non_test_file() -> None:
    patch = _diff(
        "myapp/client.py",
        [" def send_request():", "-    return call_api()", "+    return call_api(retries=3)"],
    )
    objections = s4_fix.static_precheck(patch)
    assert any("non-test file" in o.lower() for o in objections)


def test_static_precheck_allows_conftest() -> None:
    patch = _diff("tests/conftest.py", [" import pytest", "+@pytest.fixture", "+def clean_state():", "+    yield"])
    assert s4_fix.static_precheck(patch) == []


def test_static_precheck_rejects_skip_and_xfail() -> None:
    skip_patch = _diff("tests/test_api.py", [" def test_retry():", "+@pytest.mark.skip", "     assert True"])
    xfail_patch = _diff("tests/test_api.py", [" def test_retry():", "+@pytest.mark.xfail", "     assert True"])
    assert any("skip" in o.lower() for o in s4_fix.static_precheck(skip_patch))
    assert any("skip" in o.lower() for o in s4_fix.static_precheck(xfail_patch))


def test_static_precheck_rejects_retry_decorator() -> None:
    patch = _diff("tests/test_api.py", [" def test_retry():", "+@pytest.mark.flaky(reruns=3)", "     assert True"])
    objections = s4_fix.static_precheck(patch)
    assert any("retry" in o.lower() or "rerun" in o.lower() for o in objections)


def test_static_precheck_rejects_oversized_diff() -> None:
    lines = [f"+    line_{i} = {i}" for i in range(250)]
    patch = _diff("tests/test_api.py", lines)
    objections = s4_fix.static_precheck(patch)
    assert any("cap" in o.lower() or "changes" in o.lower() for o in objections)


def test_static_precheck_rejects_unparseable_patch() -> None:
    assert s4_fix.static_precheck("not a real diff") == ["Patch has no parseable diff hunks"]
