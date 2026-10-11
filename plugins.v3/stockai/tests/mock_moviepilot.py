# -*- coding: utf-8 -*-
"""
mock_moviepilot.py —— 忠实模拟 MoviePilot V3 SDK 的最小桩（联调用）。

目标：在没有真实 MoviePilot 运行时（本沙箱无 Docker / 未安装 MoviePilot）的前提下，
按 V3 契约把插件加载起来并跑通逻辑，验证：
  - app.sdk.plugin._PluginBase 生命周期（init_plugin / get_state）
  - 系统原生持久化 API（save_data / get_data / get_data_path）
  - 系统「智能助手」配置（settings.LLM_*）与 logger / scheduler
  - 插件 import 所需的 requests / apscheduler 依赖（可控伪实现）

测试可通过 set_network_error / set_llm_error 切换“行情异常 / LLM 异常”，
从而验证插件的异常处理与降级逻辑（不中断主流程）。
"""

import sys
import types
import tempfile
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional


# --------------------------- requests 伪实现 --------------------------- #
class _FakeResponse:
    """模拟 requests.Response。"""

    def __init__(self, status_code: int = 200, payload: Any = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


# 全局开关：供测试控制外部依赖是否报错
_NETWORK_ERROR = {"on": False}   # 行情接口整体报错
_LLM_ERROR = {"on": False}       # LLM 接口报错


def set_network_error(on: bool) -> None:
    _NETWORK_ERROR["on"] = on


def set_llm_error(on: bool) -> None:
    _LLM_ERROR["on"] = on


class _FakeRequests:
    """可控的 requests 替身：按 URL 返回东方财富行情 / LLM 的模拟响应。"""

    @staticmethod
    def _make_quote(code: str) -> Dict[str, Any]:
        names = {"600519": "贵州茅台", "000001": "平安银行", "300750": "宁德时代"}
        name = names.get(code, f"测试股票{code}")
        return {
            "data": {
                "f43": 1880.0, "f44": 1900.0, "f45": 1850.0, "f46": 1860.0,
                "f47": 100000, "f48": 188000000, "f57": code, "f58": name,
                "f60": 1850.0, "f168": 1.62, "f169": 30.0, "f170": 2.7,
            }
        }

    @staticmethod
    def _make_kline() -> Dict[str, Any]:
        # 近 5 日日K线：日期,开,收,高,低,量,额,振幅,涨跌幅,涨跌额,换手率
        klines = [
            "2026-01-02,1860,1880,1900,1850,100000,1.88e8,2.7,1.62,30.0,0.8",
            "2026-01-03,1880,1895,1910,1875,120000,2.28e8,1.9,0.80,15.0,1.0",
            "2026-01-04,1895,1870,1900,1860,110000,2.06e8,2.1,-1.32,-25.0,0.9",
            "2026-01-05,1870,1890,1905,1865,130000,2.46e8,2.1,1.07,20.0,1.1",
            "2026-01-06,1890,1905,1920,1885,140000,2.67e8,1.8,0.79,15.0,1.2",
        ]
        return {"data": {"klines": klines}}

    @staticmethod
    def get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if _NETWORK_ERROR["on"]:
            raise RuntimeError("模拟网络异常")
        if "push2.eastmoney.com/api/qt/stock/get" in url:
            secid = ""
            for part in url.split("&"):
                if part.startswith("secid="):
                    secid = part[len("secid="):]
            code = secid.split(".")[-1]
            return _FakeResponse(200, _FakeRequests._make_quote(code))
        if "push2his.eastmoney.com/api/qt/stock/kline" in url:
            return _FakeResponse(200, _FakeRequests._make_kline())
        return _FakeResponse(404, {})

    @staticmethod
    def post(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if _LLM_ERROR["on"]:
            return _FakeResponse(500, {"error": "internal"})
        if "chat/completions" in url:
            return _FakeResponse(200, {
                "choices": [{
                    "message": {
                        "content": "技术面：均线多头排列，量能温和放大；短期或延续震荡上行。"
                                   "风险提示：注意量能不足与外围波动。仅为技术分析参考，不构成投资建议。"
                    }
                }]
            })
        return _FakeResponse(404, {})


# --------------------------- apscheduler 伪实现 --------------------------- #
class _FakeCronTrigger:
    def __init__(self, *args: Any, **kwargs: Any):
        self.args = args
        self.kwargs = kwargs

    @classmethod
    def from_crontab(cls, expr: str) -> "_FakeCronTrigger":
        return cls(expr=expr)


# --------------------------- app.sdk 桩 --------------------------- #
class _FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        print("[MP-INFO]", *args)
    def warning(self, *args: Any, **kwargs: Any) -> None:
        print("[MP-WARN]", *args)
    def error(self, *args: Any, **kwargs: Any) -> None:
        # 联调时把错误栈也打印出来便于排查
        print("[MP-ERROR]", *args)
    def debug(self, *args: Any, **kwargs: Any) -> None:
        pass


class _FakeSettings:
    # 系统「智能助手」LLM 配置（与 main.py 中 _get_llm_config 读取的字段一致）
    LLM_API_KEY = "test-system-key"
    LLM_BASE_URL = "https://api.openai.com/v1"
    LLM_MODEL = "gpt-4o-test"


class _PluginBase:
    """
    最小化的 _PluginBase 桩，复刻插件实际用到的能力与生命周期：
    init_plugin / get_state / save_data / get_data / get_data_path /
    update_config / post_message。
    """

    plugin_name: str = ""
    plugin_desc: str = ""
    plugin_icon: str = ""
    plugin_version: str = ""
    plugin_author: str = ""
    author_url: str = ""
    plugin_config_prefix: str = ""
    plugin_order: int = 50
    auth_level: int = 1

    _enabled: bool = False
    _config: Dict[str, Any] = {}

    def __init__(self) -> None:
        self._data_store: Dict[str, Any] = {}
        self._messages: List[Dict[str, str]] = []
        self._tmp_dir: str = tempfile.mkdtemp(prefix="mp_plugin_")

    # ---- 生命周期（子类 StockAi 会覆盖 init_plugin / get_state） ----
    def init_plugin(self, config: Optional[dict] = None) -> None:
        self._config = config or {}
        self._enabled = bool(self._config.get("enabled"))

    def get_state(self) -> bool:
        return self._enabled

    # ---- 持久化（系统原生 API） ----
    def get_data_path(self) -> Path:
        p = Path(self._tmp_dir) / "plugindata"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_data(self, key: str, value: Any) -> None:
        self._data_store[key] = copy.deepcopy(value)

    def get_data(self, key: str) -> Any:
        return self._data_store.get(key)

    def update_config(self, config: Dict[str, Any]) -> None:
        self._config = config

    # ---- 消息推送（联调时记录，不真正发送） ----
    def post_message(self, title: str = "", text: str = "") -> None:
        self._messages.append({"title": title, "text": text})


def _install() -> None:
    """把 app.* 与 requests / apscheduler 注入到 sys.modules（必须在 import main 之前）。"""
    if "app" in sys.modules and getattr(sys.modules["app"], "_mock_installed", False):
        return

    app = types.ModuleType("app")
    sdk = types.ModuleType("app.sdk")

    logging_mod = types.ModuleType("app.sdk.logging")
    logging_mod.logger = _FakeLogger()

    config_mod = types.ModuleType("app.sdk.config")
    config_mod.settings = _FakeSettings()

    plugin_mod = types.ModuleType("app.sdk.plugin")
    plugin_mod._PluginBase = _PluginBase

    scheduler_mod = types.ModuleType("app.sdk.scheduler")
    scheduler_mod.add_plugin_once_job = lambda *a, **k: None
    scheduler_mod.remove_plugin_once_job = lambda *a, **k: None

    sdk.logging = logging_mod
    sdk.config = config_mod
    sdk.plugin = plugin_mod
    sdk.scheduler = scheduler_mod
    app.sdk = sdk
    app._mock_installed = True  # type: ignore[attr-defined]

    sys.modules["app"] = app
    sys.modules["app.sdk"] = sdk
    sys.modules["app.sdk.logging"] = logging_mod
    sys.modules["app.sdk.config"] = config_mod
    sys.modules["app.sdk.plugin"] = plugin_mod
    sys.modules["app.sdk.scheduler"] = scheduler_mod

    # requests 伪实现
    req_mod = types.ModuleType("requests")
    req_mod.get = _FakeRequests.get
    req_mod.post = _FakeRequests.post
    req_mod.Response = _FakeResponse
    sys.modules["requests"] = req_mod

    # apscheduler 伪实现
    ap_mod = types.ModuleType("apscheduler")
    trig_mod = types.ModuleType("apscheduler.triggers")
    cron_mod = types.ModuleType("apscheduler.triggers.cron")
    cron_mod.CronTrigger = _FakeCronTrigger
    sys.modules["apscheduler"] = ap_mod
    sys.modules["apscheduler.triggers"] = trig_mod
    sys.modules["apscheduler.triggers.cron"] = cron_mod


_install()
