from __future__ import annotations

from unittest.mock import patch

import pytest

from emailauto.core.states import OutboxStatus
from emailauto.workers import tasks as worker_tasks


@pytest.mark.django_db
def test_worker_task_releases_only_inflight_rows(dispatched_row):
    dispatched_row.status = OutboxStatus.CLAIMED
    dispatched_row.save(update_fields=["status"])

    with patch.object(worker_tasks, "send_outbox_email", side_effect=RuntimeError("boom")):
        with patch.object(worker_tasks, "release_stale_outbox") as release:
            with pytest.raises(RuntimeError):
                worker_tasks.send_outbox_email_task.run(dispatched_row.id)
            release.assert_called_once()

    dispatched_row.status = OutboxStatus.SENT
    dispatched_row.save(update_fields=["status"])

    with patch.object(worker_tasks, "send_outbox_email", side_effect=RuntimeError("boom")):
        with patch.object(worker_tasks, "release_stale_outbox") as release:
            with pytest.raises(RuntimeError):
                worker_tasks.send_outbox_email_task.run(dispatched_row.id)
            release.assert_not_called()
