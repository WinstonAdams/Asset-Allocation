"""CSV 整批匯入的寫入：主檔、月度紀錄、分類目標三張表在同一個交易內一起生效。

任一步失敗（含最後 commit）整批 rollback，資料庫維持匯入前狀態，並以 PersistenceError
往上拋（見 transaction_repository.write_transaction）。
"""

# ==== 專案內部 ====
from asset_lab.models.holding import HoldingModel
from asset_lab.models.record import MonthlyRecordModel
from asset_lab.models.target import TargetAllocationModel
from asset_lab.repositories.holding_repository import HoldingRepository
from asset_lab.repositories.record_repository import RecordRepository
from asset_lab.repositories.target_repository import TargetRepository
from asset_lab.repositories.transaction_repository import TransactionRepository


def write_import(
    *,
    transaction_repo: TransactionRepository,
    holding_repo: HoldingRepository,
    record_repo: RecordRepository,
    target_repo: TargetRepository,
    holdings: list[HoldingModel],
    records: list[MonthlyRecordModel],
    targets: list[TargetAllocationModel],
) -> None:
    """在單一交易內依序寫入主檔、月度紀錄、分類目標。

    Raises:
        PersistenceError: 任一步寫入或 commit 失敗（已 rollback，資料未變更）。
    """
    with transaction_repo.transaction() as cursor:
        holding_repo.replace_all_with_context(cursor=cursor, holdings=holdings)
        record_repo.replace_all_with_context(cursor=cursor, records=records)
        target_repo.upsert_targets_with_context(cursor=cursor, targets=targets)
