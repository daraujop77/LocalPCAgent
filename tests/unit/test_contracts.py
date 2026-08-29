from personal_ai.contracts import ToolResult


def test_tool_result_is_structured_and_json_friendly() -> None:
    result = ToolResult(
        success=True,
        tool="example.inspect",
        action="inspect",
        target="sample",
        summary="Inspected sample.",
        changed_files=("sample.txt",),
        warnings=("This is a test.",),
        approval_level=0,
    )

    payload = result.to_dict()

    assert payload["success"] is True
    assert payload["changed_files"] == ["sample.txt"]
    assert payload["warnings"] == ["This is a test."]
