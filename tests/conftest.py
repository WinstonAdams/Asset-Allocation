# ==== 原生（標準庫） ====
# 無

# ==== 第三方套件 ====
# 無

# ==== 專案內部 ====
# 無


def pytest_configure(config):
    """註冊 scenario marker，讓 test 可綁定對應的 Scenario ID。

    Args:
        config: pytest 設定物件。
    """
    config.addinivalue_line("markers", "scenario(id): bind test to scenario ID")
