from pathlib import Path

import pytest

from litman_core.errors import CORE_ERROR_CODES, CoreError


def test_valid_code_is_accepted_with_optional_local_path():
    error = CoreError("invalid_input", "boom")
    assert error.code == "invalid_input"
    assert error.message == "boom"
    assert error.local_path is None
    assert str(error) == "boom"


def test_local_path_is_preserved_when_given():
    error = CoreError("analysis_failed", "boom", Path("/run"))
    assert error.local_path == Path("/run")


def test_unknown_code_is_rejected():
    with pytest.raises(ValueError):
        CoreError("not_a_code", "boom")


def test_core_error_codes_is_the_closed_set():
    assert CORE_ERROR_CODES == (
        "invalid_config",
        "invalid_input",
        "llm_unavailable",
        "analysis_failed",
        "publication_failed",
        "internal",
    )
