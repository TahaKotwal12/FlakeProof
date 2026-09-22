"""Unit tests for flakeproof.pytest_parse: JUnit XML parsing edge cases
(namespaced properties, reruns, timeouts, both testsuites/testsuite root
shapes) and nodeid resolution via match_node_ids.
"""

from __future__ import annotations

from flakeproof import pytest_parse as pp


def test_classname_and_name_for_nodeid_plain_function() -> None:
    assert pp.classname_and_name_for_nodeid("tests/test_api.py::test_retry") == ("tests.test_api", "test_retry")


def test_classname_and_name_for_nodeid_nested_class() -> None:
    assert pp.classname_and_name_for_nodeid("tests/test_api.py::TestFoo::test_method") == (
        "tests.test_api.TestFoo",
        "test_method",
    )


def test_classname_and_name_for_nodeid_parametrized() -> None:
    assert pp.classname_and_name_for_nodeid("tests/test_api.py::test_thing[param1]") == (
        "tests.test_api",
        "test_thing[param1]",
    )


def test_classname_and_name_for_nodeid_nested_dir() -> None:
    assert pp.classname_and_name_for_nodeid("tests/sub/test_api.py::test_x") == ("tests.sub.test_api", "test_x")


_XUNIT2_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" errors="0" failures="1" skipped="1" tests="4" time="1.5">
    <properties>
      <property name="ci:build_id" value="1234"/>
      <property name="env:python_version" value="3.12"/>
    </properties>
    <testcase classname="tests.test_api" name="test_get" time="0.010"/>
    <testcase classname="tests.test_api" name="test_retry" time="0.045">
      <failure message="AssertionError: assert 1 == 2">Traceback (most recent call last):
E   AssertionError: assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.test_api" name="test_slow" time="5.002">
      <failure message="Failed: Timeout &gt;5.0s">Traceback...</failure>
    </testcase>
    <testcase classname="tests.test_api" name="test_skip_me" time="0.001">
      <skipped message="not implemented"/>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_xml_xunit2_root_and_outcomes() -> None:
    results = pp.parse_junit_xml(_XUNIT2_XML)
    by_name = {r.name: r for r in results}
    assert by_name["test_get"].outcome == "passed"
    assert by_name["test_retry"].outcome == "failed"
    assert by_name["test_retry"].message == "AssertionError: assert 1 == 2"
    assert by_name["test_slow"].outcome == "timeout"
    assert by_name["test_skip_me"].outcome == "skipped"


def test_parse_junit_xml_tolerates_namespaced_properties() -> None:
    # Would raise/miss data if <properties> traversal broke parsing.
    results = pp.parse_junit_xml(_XUNIT2_XML)
    assert len(results) == 4


_BARE_TESTSUITE_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuite name="pytest" tests="1" failures="0">
  <testcase classname="tests.test_cache" name="test_set" time="0.02"/>
</testsuite>
"""


def test_parse_junit_xml_bare_testsuite_root() -> None:
    results = pp.parse_junit_xml(_BARE_TESTSUITE_XML)
    assert len(results) == 1
    assert results[0].classname == "tests.test_cache"
    assert results[0].outcome == "passed"


_RERUN_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="2">
    <testcase classname="tests.test_flaky" name="test_eventually_passes" time="0.3">
      <rerun message="AssertionError: assert 1 == 2">Traceback...</rerun>
      <rerun message="AssertionError: assert 1 == 2">Traceback...</rerun>
    </testcase>
    <testcase classname="tests.test_flaky" name="test_never_passes" time="0.3">
      <rerun message="AssertionError: assert 1 == 2">Traceback...</rerun>
      <failure message="AssertionError: assert 1 == 2">Traceback...</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


def test_parse_junit_xml_reruns_use_final_outcome_not_rerun_count() -> None:
    results = pp.parse_junit_xml(_RERUN_XML)
    by_name = {r.name: r for r in results}
    # Eventually-passing test: only <rerun> children (no failure/error) -> passed, but reruns counted.
    assert by_name["test_eventually_passes"].outcome == "passed"
    assert by_name["test_eventually_passes"].rerun_count == 2
    # Still failing after reruns: final <failure> child wins.
    assert by_name["test_never_passes"].outcome == "failed"
    assert by_name["test_never_passes"].rerun_count == 1


def test_match_node_ids_resolves_plain_and_class_scoped_tests() -> None:
    testcases = [
        pp.TestCaseResult("tests.test_api", "test_get", "passed", 0.01, None, None, 0),
        pp.TestCaseResult("tests.test_api.TestFoo", "test_method", "failed", 0.02, "boom", "trace", 0),
    ]
    known = ["tests/test_api.py::test_get", "tests/test_api.py::TestFoo::test_method"]
    resolved = pp.match_node_ids(testcases, known)
    nodeids = {r.nodeid for r in resolved}
    assert nodeids == set(known)


def test_match_node_ids_drops_unknown_testcases() -> None:
    testcases = [pp.TestCaseResult("tests.test_api", "test_ghost", "passed", 0.0, None, None, 0)]
    resolved = pp.match_node_ids(testcases, ["tests/test_api.py::test_get"])
    assert resolved == []


def test_parse_pytest_stdout_fallback() -> None:
    stdout = (
        "tests/test_api.py::test_get PASSED\n"
        "tests/test_api.py::test_retry FAILED\n"
        "tests/test_api.py::test_skip SKIPPED\n"
        "some unrelated log line\n"
    )
    results = pp.parse_pytest_stdout(stdout)
    outcomes = {r.name: r.outcome for r in results}
    assert outcomes == {"test_get": "passed", "test_retry": "failed", "test_skip": "skipped"}
