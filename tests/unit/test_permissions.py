from datetime import UTC, datetime, timedelta

import pytest

from personal_ai.permissions import PermissionPolicy, PermissionServiceError
from tests.support import make_permission_service


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 29, tzinfo=UTC)

    def __call__(self):
        return self.now


def test_safe_action_is_authorized_automatically() -> None:
    permissions = make_permission_service()

    decision = permissions.authorize("pc.system_info")

    assert decision.allowed is True
    assert decision.level == 0
    assert decision.automatic is True
    assert permissions.list_requests() == []


def test_destructive_approval_is_scoped_and_one_time() -> None:
    permissions = make_permission_service()
    parameters = {"text": "approved text"}
    pending = permissions.authorize("pc.input.type", parameters=parameters)
    approval_id = pending.approval.approval_id
    permissions.decide(approval_id, "accepted", decided_by="test-user")

    mismatch = permissions.authorize(
        "pc.input.type",
        parameters={"text": "different text"},
        approval_id=approval_id,
    )
    accepted = permissions.authorize(
        "pc.input.type",
        parameters=parameters,
        approval_id=approval_id,
    )
    reused = permissions.authorize(
        "pc.input.type",
        parameters=parameters,
        approval_id=approval_id,
    )

    assert mismatch.error == "approval_scope_mismatch"
    assert accepted.allowed is True
    assert accepted.approval.consumed_at is not None
    assert reused.error == "approval_already_used"


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [("rejected", "approval_rejected"), ("cancelled", "approval_cancelled")],
)
def test_nonaccepted_decisions_never_authorize(status, expected_error) -> None:
    permissions = make_permission_service()
    pending = permissions.authorize("pc.input.click", parameters={"x": 1, "y": 2})
    approval_id = pending.approval.approval_id
    permissions.decide(approval_id, status)

    decision = permissions.authorize(
        "pc.input.click",
        parameters={"x": 1, "y": 2},
        approval_id=approval_id,
    )

    assert decision.allowed is False
    assert decision.error == expected_error


def test_approval_expires_before_execution() -> None:
    clock = MutableClock()
    permissions = make_permission_service(clock=clock)
    pending = permissions.authorize("pc.apps.close", target="notepad.exe")
    approval_id = pending.approval.approval_id
    permissions.decide(approval_id, "accepted")
    clock.now += timedelta(seconds=permissions.policy.approval_ttl_seconds + 1)

    decision = permissions.authorize(
        "pc.apps.close",
        target="notepad.exe",
        approval_id=approval_id,
    )

    assert decision.allowed is False
    assert decision.error == "approval_expired"


def test_privileged_action_fails_closed_and_does_not_consume_approval() -> None:
    permissions = make_permission_service()
    parameters = {"operation": "fixture"}
    pending = permissions.authorize("privileged.system.execute", parameters=parameters)
    approval_id = pending.approval.approval_id
    permissions.decide(approval_id, "accepted")

    decision = permissions.authorize(
        "privileged.system.execute",
        parameters=parameters,
        approval_id=approval_id,
    )

    assert decision.allowed is False
    assert decision.error == "privileged_helper_unavailable"
    assert permissions.get(approval_id).consumed_at is None


def test_automatic_action_rejects_unnecessary_approval_request() -> None:
    permissions = make_permission_service()

    with pytest.raises(PermissionServiceError, match="pc.system_info") as error:
        permissions.request_approval("pc.system_info")

    assert error.value.code == "approval_not_required"


def test_policy_validation_fails_closed_on_incomplete_configuration(tmp_path) -> None:
    policy = tmp_path / "permissions.yaml"
    policy.write_text('{"version": 1}', encoding="utf-8")

    with pytest.raises(PermissionServiceError) as error:
        PermissionPolicy.load(policy)

    assert error.value.code == "approval_ttl_invalid"
