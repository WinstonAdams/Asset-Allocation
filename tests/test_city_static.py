"""城市總覽的靜態檢查：相依下限、元件資源檔、前端安全與契約掃描。

JS 行為無自動化測試，以靜態掃描加人工目視清單兜底（打包內容另以 uv build 人工核對）。
"""

# ==== 原生（標準庫） ====
import ast
import json
import re
import tomllib
from pathlib import Path

# ==== 第三方套件 ====
import pytest

# ==== 專案內部 ====
from asset_lab.city import component
from asset_lab.city.geometry import GEOMETRY, geometry_json
from tests.test_city_payload import _build

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


# ---------------------------------------------------------------------------
# 前端安全與契約掃描
# ---------------------------------------------------------------------------

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?m)(?:^|(?<=\s))//.*$")
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]")
_MARKUP_API = re.compile(
    r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|DOMParser|createContextualFragment"
    r"|\beval\s*\(|new\s+Function"
)
# 會把字串當成程式或網址載入的寫法：事件屬性、src／href／srcdoc、字串形式的計時器
_SCRIPT_SINK_API = re.compile(
    r"setAttribute\s*\(\s*['\"`](?:on|src\b|href\b|srcdoc\b)"
    r"|\.(?:src|href|srcdoc)\s*=(?!=)"
    r"|\bset(?:Timeout|Interval)\s*\(\s*['\"`]",
    re.IGNORECASE,
)
_SCRIPT_SINK_SAMPLES = (
    "el.setAttribute('onclick', name)",
    'el.setAttribute("ONERROR", name)',
    "img.setAttribute('src', url)",
    "img.src = url",
    "a.href = url",
    "frame.srcdoc = html",
    "setTimeout('run()', 10)",
    "setInterval(`tick()`, 10)",
)
_GEOM_NAMES = r"TW|TH|HMAX|UX|VY|LAB|FR|EPS|FLAG_[A-Z_]+|SC_MAX|NARROW|OVERLAY|SIDE|SOIL"
_REDECLARED_GEOM = re.compile(rf"\b(?:const|let|var)\s+(?:{_GEOM_NAMES})\b")
_FORBIDDEN_CITY_REFERENCES = (
    "st.user",
    "st.login",
    "st.logout",
    "st.secrets",
    "bootstrap",
    "repositories",
    "get_container",
)
_BUILDING_KEYS = {
    "id", "name", "zone", "kind", "shape", "lot", "plate", "value",
    "vacant", "plate_mode", "sub", "tip", "warn",
}  # fmt: skip
_SITE_KEYS = {"id", "name", "lot", "plate", "progress", "sub", "tip", "flags"}
_PAYLOAD_KEYS = {
    "month", "aria_label", "ground", "top_pad", "compact", "roads", "blocks", "max_asset",
    "max_liab", "weather", "buildings", "site", "selected",
}  # fmt: skip


def _js_code() -> str:
    """city.js 去掉註解後的程式碼（註解可以有中文，程式碼不行）。"""
    text = (CITY_DIR / "city.js").read_text(encoding="utf-8")
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _city_python_files() -> list[Path]:
    return sorted(CITY_DIR.glob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.scenario("SC-155")
def test_sc155_js_never_parses_markup():
    assert _MARKUP_API.search(_js_code()) is None


@pytest.mark.scenario("SC-155")
def test_sc155_js_never_loads_strings_as_script_or_url():
    assert _SCRIPT_SINK_API.search(_js_code()) is None


@pytest.mark.scenario("SC-155")
@pytest.mark.parametrize("sample", _SCRIPT_SINK_SAMPLES)
def test_sc155_script_sink_scan_catches_each_forbidden_form(sample):
    assert _SCRIPT_SINK_API.search(sample) is not None


@pytest.mark.scenario("SC-155")
def test_sc155_script_sink_scan_allows_safe_attributes_and_timers():
    for sample in (
        "canvas.setAttribute('aria-label', label)",
        "if (a.src === b.src) run()",
        "setTimeout(() => run(), 10)",
    ):
        assert _SCRIPT_SINK_API.search(sample) is None, sample


@pytest.mark.scenario("SC-155")
def test_sc155_js_builds_dom_text_with_text_content():
    code = _js_code()

    assert "createElement" in code
    assert "textContent" in code


@pytest.mark.scenario("SC-155")
def test_sc155_label_colors_enforce_minimum_contrast():
    code = _js_code()

    assert re.search(r"contrast\([^)]*\)\s*<\s*4\.5", code), "名稱牌文字色必須檢查對比 4.5"


@pytest.mark.scenario("SC-156")
def test_sc156_city_modules_do_not_reference_identity_secrets_or_data_layer():
    for path in _city_python_files():
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_CITY_REFERENCES:
            assert token not in text, f"{path.name} 引用了 {token}"


@pytest.mark.scenario("SC-156")
def test_sc156_only_component_module_imports_streamlit():
    for path in _city_python_files():
        imports_streamlit = "streamlit" in _imported_roots(path)
        assert imports_streamlit == (path.name == "component.py"), path.name


@pytest.mark.scenario("SC-156")
def test_sc156_payload_carries_only_display_fields():
    payload = _build()

    assert set(payload) == _PAYLOAD_KEYS
    assert payload["buildings"]
    for entry in payload["buildings"]:
        assert set(entry) == _BUILDING_KEYS
    assert set(payload["site"]) == _SITE_KEYS
    json.dumps(payload)


@pytest.mark.scenario("SC-156")
def test_sc156_js_has_no_business_text_outside_comments():
    assert _CJK.search(_js_code()) is None


@pytest.mark.scenario("SC-156")
def test_sc156_js_reads_geometry_from_injected_constant_only():
    code = _js_code()

    assert "GEOM." in code
    assert _REDECLARED_GEOM.search(code) is None


@pytest.mark.scenario("SC-156")
def test_sc156_js_reports_selection_only_as_state_value():
    code = _js_code()

    assert "setTriggerValue" not in code
    assert re.search(r"setStateValue\(\s*['\"]selected['\"]", code)


@pytest.mark.scenario("SC-156")
def test_sc156_js_keeps_instances_in_weakmap_without_diagnostic_leftovers():
    code = _js_code()

    assert "new WeakMap" in code
    assert "__city" not in code
    assert "dbg" not in code


@pytest.mark.scenario("SC-156")
def test_sc156_js_follows_payload_state_contract():
    code = _js_code()

    for token in ("plate_mode", "faded", "hidden", "vacant", "calm", "weather.sky", "compact"):
        assert token in code, f"city.js 未處理 payload 契約項 {token}"


@pytest.mark.scenario("SC-156")
def test_sc156_component_script_prefixes_geometry_constant():
    script = component.component_script()
    first_line, _, rest = script.partition("\n")
    match = re.fullmatch(r"const GEOM = (.*);", first_line)

    assert match is not None
    assert json.loads(match.group(1)) == json.loads(geometry_json())
    assert json.loads(match.group(1))["tw"] == GEOMETRY.tw
    assert rest == (CITY_DIR / "city.js").read_text(encoding="utf-8")


@pytest.mark.scenario("SC-156")
def test_sc156_component_html_has_no_text_or_diagnostics():
    assert _CJK.search(component.COMPONENT_HTML) is None
    assert "dbg" not in component.COMPONENT_HTML


@pytest.mark.scenario("SC-148")
def test_sc164_css_defines_neutral_weather_severity_without_diagnostics():
    css = (CITY_DIR / "city.css").read_text(encoding="utf-8")

    assert 'data-sev="neutral"' in css
    assert ".dbg" not in css


@pytest.mark.scenario("SC-166")
def test_sc166_js_honors_reduced_motion_preference():
    code = _js_code()

    assert "prefers-reduced-motion" in code
