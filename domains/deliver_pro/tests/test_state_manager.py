"""Tests for DeliverProStateManager contract cage.

AgentDryRun V3.7 (2026-07-30): DeliverProStateManager 已废弃，
实例化时 raise ValueError（契约笼子防呆）。
"""
import pytest
from domains.deliver_pro.state_manager import DeliverProStateManager, StateTransitionError


class TestDeliverProStateManagerContractCage:
    """契约笼子：实例化时 raise ValueError。"""

    def test_instantiation_raises_value_error(self):
        """DeliverProStateManager() must raise ValueError."""
        with pytest.raises(ValueError, match="DEPRECATED"):
            DeliverProStateManager(blackboard=None)

    def test_instantiation_with_args_raises(self):
        """DeliverProStateManager(*args, **kwargs) must raise ValueError."""
        with pytest.raises(ValueError, match="contract cage"):
            DeliverProStateManager("anything", key="value")

    def test_error_message_mentions_alternative(self):
        """Error message should guide to the correct alternative."""
        with pytest.raises(ValueError) as exc_info:
            DeliverProStateManager(None)
        assert "DeliverWPRunner" in str(exc_info.value)


class TestStateTransitionError:
    """StateTransitionError 保留用于其他模块兼容。"""

    def test_can_instantiate(self):
        """StateTransitionError can still be instantiated."""
        err = StateTransitionError("test error")
        assert str(err) == "test error"

    def test_is_exception(self):
        """StateTransitionError is an Exception."""
        assert issubclass(StateTransitionError, Exception)
