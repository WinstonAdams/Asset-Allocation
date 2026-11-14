"""城市總覽的靜態檢查：相依下限與元件資源檔（打包內容另以 uv build 人工核對）。"""

# ==== 原生（標準庫） ====
import re
import tomllib
from pathlib import Path

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
# 無

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CITY_DIR = PROJECT_ROOT / "src" / "asset_lab" / "city"
MIN_STREAMLIT = (1, 66)
EXTERNAL_URL_PATTERN = re.compile(r"https?://|@import\s+url|//cdn\.", re.IGNORECASE)


def _dependencies() -> list[str]:
    """讀 pyproject.toml 的執行期相依宣告。"""
    data = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["dependencies"]


@pytest.mark.scenario("SC-164")
def test_sc164_streamlit_lower_bound_supports_components_v2():
    spec = next(dep for dep in _dependencies() if dep.startswith("streamlit"))
    match = re.search(r">=\s*(\d+)\.(\d+)", spec)

    assert match is not None
    assert (int(match.group(1)), int(match.group(2))) >= MIN_STREAMLIT


@pytest.mark.scenario("SC-164")
def test_sc164_component_script_and_style_files_exist():
    for name in ("city.js", "city.css"):
        path = CITY_DIR / name
        assert path.is_file(), f"缺少城市元件資源檔 {name}"
        assert path.read_text(encoding="utf-8").strip()


@pytest.mark.scenario("SC-164")
def test_sc164_no_new_third_party_dependency():
    names = {re.split(r"[\[<>=!~ ]", dep, maxsplit=1)[0] for dep in _dependencies()}

    assert names == {"streamlit", "libsql", "pyxirr", "plotly", "pandas", "pydantic"}


@pytest.mark.scenario("SC-164")
def test_sc164_component_assets_load_no_external_resources():
    for name in ("city.js", "city.css"):
        text = (CITY_DIR / name).read_text(encoding="utf-8")
        assert EXTERNAL_URL_PATTERN.search(text) is None, f"{name} 引用外部資源"
