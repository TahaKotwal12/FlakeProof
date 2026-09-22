"""JUnit XML / pytest output parsing into structured test results.

pytest's junitxml `<testcase>` elements don't carry the full pytest nodeid --
only `classname` (dotted module path, with any test class names appended)
and `name` (the function/method name, `[params]` suffix included for
parametrized tests). Reversing `classname` back into a `path/to.py` +
`::Class::method` nodeid is ambiguous in general (dots separate both
directory segments AND class nesting), so `parse_junit_xml` returns raw
`(classname, name)`-keyed results and `match_node_ids` resolves them against
the *known* nodeid list every stage already has (S1's
`pytest --collect-only` output, seeded into `test_stats`) by forward-deriving
each known nodeid's own `(classname, name)` the same way pytest's junit
writer does, then joining on that -- exact, and unambiguous regardless of
test-class nesting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree as ET

TestOutcome = str  # 'passed' | 'failed' | 'error' | 'skipped' | 'timeout'

# docs/02-DATABASE.md: test_results.failure_log is "truncated to 8 KB".
_LOG_TAIL_MAX_CHARS = 8000

_TIMEOUT_MESSAGE_RE = re.compile(r"\btimeout\b", re.IGNORECASE)

# pytest -q / -v result lines: 'tests/test_api.py::test_name PASSED' (plain stdout
# fallback parser, used when a branch crashed before writing JUnit XML at all).
_STDOUT_RESULT_RE = re.compile(r"^(?P<nodeid>\S+::\S+)\s+(?P<outcome>PASSED|FAILED|ERROR|SKIPPED)\b")


@dataclass(frozen=True)
class TestCaseResult:
    """One `<testcase>` from a JUnit XML report, keyed by pytest's own identity
    (`classname`, `name`) rather than a nodeid -- see module docstring.
    """

    classname: str
    name: str
    outcome: TestOutcome
    duration_s: float
    message: str | None
    log_tail: str | None
    rerun_count: int


@dataclass(frozen=True)
class TestResult:
    """A `TestCaseResult` resolved to its real pytest nodeid via `match_node_ids`."""

    nodeid: str
    outcome: TestOutcome
    duration_s: float
    message: str | None
    log_tail: str | None
    rerun_count: int


def _tail(text: str, max_chars: int = _LOG_TAIL_MAX_CHARS) -> str:
    return text if len(text) <= max_chars else text[-max_chars:]


def _iter_testsuite_elements(root: ET.Element) -> list[ET.Element]:
    """Handles both the `<testsuites><testsuite>...` root (xunit2, pytest's
    default since 6.0) and a bare `<testsuite>` root (older/other tooling).
    """
    if root.tag == "testsuites":
        return list(root.findall("testsuite"))
    if root.tag == "testsuite":
        return [root]
    return []


def _outcome_and_detail(testcase: ET.Element) -> tuple[TestOutcome, str | None, str | None]:
    """A `<testcase>` is `passed` unless it has a failure/error/skipped child.

    With `pytest-rerunfailures`, earlier failed attempts show up as `<rerun>`
    elements, but the testcase's own final failure/error/skipped child (or
    none, if the last attempt passed) is still what decides the outcome --
    `<rerun>` elements are counted, never treated as the result. The
    `pytest-timeout` plugin raises `Failed: Timeout >Ns` inside a `<failure>`;
    we special-case that into outcome=`timeout` since docs/02-DATABASE.md's
    `test_outcome` enum distinguishes it from a generic failure.
    """
    failure = testcase.find("failure")
    error = testcase.find("error")
    skipped = testcase.find("skipped")

    if failure is not None:
        message = failure.get("message")
        outcome = "timeout" if message and _TIMEOUT_MESSAGE_RE.search(message) else "failed"
        return outcome, message, failure.text
    if error is not None:
        message = error.get("message")
        outcome = "timeout" if message and _TIMEOUT_MESSAGE_RE.search(message) else "error"
        return outcome, message, error.text
    if skipped is not None:
        return "skipped", skipped.get("message"), skipped.text
    return "passed", None, None


def parse_junit_xml(xml_text: str) -> list[TestCaseResult]:
    """Parse a JUnit XML report produced by `pytest --junitxml` into `TestCaseResult` rows.

    Tolerates `<properties>` blocks (including namespaced property names like
    `ci:build_id`, which some CI setups add via conftest) -- they're simply
    not traversed, since `classname`/`name` alone already uniquely key a
    testcase within one report.
    """
    root = ET.fromstring(xml_text)
    results: list[TestCaseResult] = []
    for suite in _iter_testsuite_elements(root):
        for testcase in suite.findall("testcase"):
            classname = testcase.get("classname", "")
            name = testcase.get("name", "")
            duration_s = float(testcase.get("time") or 0.0)
            outcome, message, log_tail = _outcome_and_detail(testcase)
            results.append(
                TestCaseResult(
                    classname=classname,
                    name=name,
                    outcome=outcome,
                    duration_s=duration_s,
                    message=message.strip() if message else None,
                    log_tail=_tail(log_tail.strip()) if log_tail and log_tail.strip() else None,
                    rerun_count=len(testcase.findall("rerun")),
                )
            )
    return results


def classname_and_name_for_nodeid(node_id: str) -> tuple[str, str]:
    """Forward-derive the `(classname, name)` pytest's junit writer would use for
    a known nodeid, e.g. `tests/test_api.py::TestFoo::test_method` ->
    `('tests.test_api.TestFoo', 'test_method')`. Unambiguous in this
    direction, unlike reversing `classname` back into a nodeid.
    """
    file_part, _, rest = node_id.partition("::")
    module = file_part.removesuffix(".py")
    module_dotted = module.replace("/", ".")
    if not rest:
        return module_dotted, ""
    parts = rest.split("::")
    name = parts[-1]
    class_chain = parts[:-1]
    classname = ".".join([module_dotted, *class_chain]) if class_chain else module_dotted
    return classname, name


def match_node_ids(testcases: list[TestCaseResult], known_node_ids: list[str]) -> list[TestResult]:
    """Resolve each `TestCaseResult` to its real nodeid by joining on
    `(classname, name)` against `known_node_ids` (S1's collected node-id
    list). Testcases with no matching known nodeid are dropped -- e.g. a
    pytest-generated pseudo-testcase for a collection/setup error -- rather
    than guessed at.
    """
    by_identity = {classname_and_name_for_nodeid(nid): nid for nid in known_node_ids}
    resolved: list[TestResult] = []
    for tc in testcases:
        nodeid = by_identity.get((tc.classname, tc.name))
        if nodeid is None:
            continue
        resolved.append(
            TestResult(
                nodeid=nodeid,
                outcome=tc.outcome,
                duration_s=tc.duration_s,
                message=tc.message,
                log_tail=tc.log_tail,
                rerun_count=tc.rerun_count,
            )
        )
    return resolved


def parse_pytest_stdout(stdout: str) -> list[TestCaseResult]:
    """Fallback parser for plain pytest stdout when JUnit XML isn't available
    (e.g. the sandbox run crashed before pytest could write the report).
    Parses `-v`/`-q` style result lines: `path/to/test.py::test_name PASSED`.
    No duration/message/rerun data is available from this format.
    """
    outcome_map = {"PASSED": "passed", "FAILED": "failed", "ERROR": "error", "SKIPPED": "skipped"}
    results: list[TestCaseResult] = []
    for line in stdout.splitlines():
        match = _STDOUT_RESULT_RE.match(line.strip())
        if not match:
            continue
        classname, name = classname_and_name_for_nodeid(match.group("nodeid"))
        results.append(
            TestCaseResult(
                classname=classname,
                name=name,
                outcome=outcome_map[match.group("outcome")],
                duration_s=0.0,
                message=None,
                log_tail=None,
                rerun_count=0,
            )
        )
    return results
