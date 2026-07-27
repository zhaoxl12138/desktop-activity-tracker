"""Safe, shared shutdown protocol for the GUI recording worker."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SHUTDOWN_WAIT_MS = 15_000
MAX_SHUTDOWN_WAIT_MS = 15_000


@dataclass(frozen=True)
class WorkerShutdownResult:
    """Outcome of a worker shutdown request.

    The worker reference is intentionally retained in both outcomes. A caller
    must not drop a still-running QThread merely because the wait budget
    expired.
    """

    completed: bool
    worker: object | None
    timeout_ms: int
    message: str = ""


def _resolve_wait_budget_ms(worker: object, timeout_ms: int | None) -> int:
    if timeout_ms is not None:
        return min(MAX_SHUTDOWN_WAIT_MS, max(1, int(timeout_ms)))

    configured_budget = getattr(worker, "shutdown_wait_budget_ms", None)
    try:
        value = configured_budget() if callable(configured_budget) else configured_budget
        if value is not None:
            return min(MAX_SHUTDOWN_WAIT_MS, max(1, int(value)))
    except (TypeError, ValueError):
        pass
    return DEFAULT_SHUTDOWN_WAIT_MS


def stop_recording_worker_safely(
    worker: object | None,
    *,
    timeout_ms: int | None = None,
) -> WorkerShutdownResult:
    """Stop a recording worker and wait for its persistence cleanup.

    This helper never terminates or deletes a timed-out thread. Callers must
    check ``completed`` before quitting Qt, scheduling a restart, or closing
    shared runtime database state.
    """

    if worker is None:
        return WorkerShutdownResult(True, None, 0)

    budget_ms = _resolve_wait_budget_ms(worker, timeout_ms)
    try:
        worker.stop()
        completed = bool(worker.wait(budget_ms))
    except Exception as exc:
        return WorkerShutdownResult(
            completed=False,
            worker=worker,
            timeout_ms=budget_ms,
            message=(
                "The recording worker could not be stopped safely "
                f"({exc}). Runtime data was not closed; retry after checking "
                "the recording status."
            ),
        )

    if completed:
        health = getattr(worker, "health", None)
        status = str(getattr(health, "status", "") or "")
        pending = max(0, int(getattr(health, "pending_persists", 0) or 0))
        recovery_path = str(getattr(health, "recovery_path", "") or "")
        recovery_status = str(
            getattr(health, "recovery_status", "") or ""
        )
        explicitly_safe = getattr(health, "shutdown_safe", None)
        if pending or explicitly_safe is False:
            details = [f"status={status or 'unknown'}"]
            if pending:
                details.append(f"volatile pending sessions={pending}")
            if recovery_status:
                details.append(f"recovery={recovery_status}")
            if recovery_path:
                details.append(f"path={recovery_path}")
            return WorkerShutdownResult(
                completed=False,
                worker=worker,
                timeout_ms=budget_ms,
                message=(
                    "The recording worker joined but shutdown is not safe ("
                    + ", ".join(details)
                    + "). Runtime data was not closed."
                ),
            )
        return WorkerShutdownResult(True, worker, budget_ms)

    return WorkerShutdownResult(
        completed=False,
        worker=worker,
        timeout_ms=budget_ms,
        message=(
            "The recording worker did not finish its session-persistence "
            f"cleanup within {budget_ms / 1000:.1f} seconds. The application "
            "and runtime data were not closed. Wait for cleanup, then retry."
        ),
    )
