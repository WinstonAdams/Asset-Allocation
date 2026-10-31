"""測試用：包真實連線，在第 N 次 execute 注入失敗，供整批寫入的中途失敗情境共用。"""


class _FailingCursor:
    """包真實 cursor：第 fail_at 次 execute 拋錯。"""

    def __init__(self, real_cursor, *, fail_at: int) -> None:
        self._real_cursor = real_cursor
        self._fail_at = fail_at
        self._calls = 0

    def execute(self, *args: object, **kwargs: object):
        self._calls += 1
        if self._calls == self._fail_at:
            raise RuntimeError("模擬寫入中途失敗")
        return self._real_cursor.execute(*args, **kwargs)

    def __getattr__(self, name: str):
        # 其餘（fetchall 等）交給真實 cursor，讓讀取路徑也能走同一個替身連線
        return getattr(self._real_cursor, name)


class FlakyConnection:
    """包真實連線：cursor 在第 fail_at 次 execute 失敗；可選 commit 失敗或 rollback 失敗。"""

    def __init__(
        self,
        real_conn,
        *,
        fail_at: int = 0,
        commit_fails: bool = False,
        rollback_fails: bool = False,
    ) -> None:
        self._real_conn = real_conn
        self._fail_at = fail_at
        self._commit_fails = commit_fails
        self._rollback_fails = rollback_fails

    def cursor(self):
        return _FailingCursor(self._real_conn.cursor(), fail_at=self._fail_at)

    def commit(self):
        if self._commit_fails:
            raise RuntimeError("模擬 commit 失敗")
        self._real_conn.commit()

    def rollback(self):
        if self._rollback_fails:
            raise RuntimeError("模擬 rollback 失敗")
        self._real_conn.rollback()
