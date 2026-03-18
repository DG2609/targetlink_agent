"""
DEPRECATED: Routing logic đã chuyển sang pipeline/state_machine.py.

Import mới nên dùng:
    from pipeline.state_machine import RetryStateMachine, RetryState

File này giữ lại để backward-compatible imports không bị lỗi.
"""

from pipeline.state_machine import RetryStateMachine, RetryState

__all__ = ["RetryStateMachine", "RetryState"]
