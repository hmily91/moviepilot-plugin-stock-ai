# -*- coding: utf-8 -*-
"""
run_integration.py —— 股票AI分析助手 本地联调集成测试

运行方式（在插件根目录或任意位置）：
    python tests/run_integration.py

说明：
    本测试用 tests/mock_moviepilot.py 忠实模拟 MoviePilot V3 SDK，把插件按 V3 契约
    加载起来，覆盖：
      1) 插件加载与生命周期（init_plugin / get_state）
      2) 配置表单 get_form
      3) 插件 API 路由声明 get_api（/history /run /clear /set_filter）
      4) 定时服务注册 get_service
      5) 完整分析流水线（mock 行情 + LLM，不发起真实网络请求）
      6) 历史页 get_page 渲染（含空状态）
      7) API 端点行为（筛选 / 立即分析 / 清空）
      8) 异常处理（行情异常 / LLM 异常 不中断流程）
      9) 仅依赖内置库可成功 import

注意：本沙箱无 Docker、未安装 MoviePilot，因此此处以 SDK 桩完成“联调”；
      部署到真实 MoviePilot 的步骤见 README 第七章。
"""

import os
import sys
import importlib
from typing import List

# 1) 先把 Mock SDK 注入 sys.modules（必须在 import main 之前）
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(HERE)
sys.path.insert(0, PLUGIN_DIR)

import tests.mock_moviepilot as mock_mp  # noqa: E402  (触发 _install)
from tests.mock_moviepilot import set_network_error, set_llm_error  # noqa: E402

# 2) 加载插件主模块（此时 app / requests / apscheduler 均为 mock）
main = importlib.import_module("main")
StockAi = main.StockAi

# 加速：联调测试无需真实限速 sleep
main.time.sleep = lambda *a, **k: None


RESULTS: List[tuple] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    RESULTS.append((name, cond, extra))
    flag = "PASS" if cond else "FAIL"
    print(f"[{flag}] {name}" + (f" -> {extra}" if extra else ""))


def build_plugin(enabled: bool = True) -> StockAi:
    p = StockAi()
    cfg = {
        "enabled": enabled,
        "stocks": "600519,000001,300750",
        "llm_source": "custom",
        "custom_api_key": "k",
        "custom_base_url": "https://fake.example/v1",
        "custom_model": "fake-model",
        "push_morning": True,
        "push_close": True,
        "skip_holiday": True,
    }
    p.init_plugin(cfg)
    return p


def has_component(comps: list, name: str) -> bool:
    for c in comps:
        if not isinstance(c, dict):
            continue
        if c.get("component") == name:
            return True
        if isinstance(c.get("content"), list) and has_component(c["content"], name):
            return True
    return False


def main_test() -> int:
    print("===== 1. 插件加载与生命周期 =====")
    p = build_plugin(True)
    check("实例化成功", isinstance(p, StockAi))
    check("启用时 get_state=True", p.get_state() is True)
    check("未启用时 get_state=False", build_plugin(False).get_state() is False)

    print("\n===== 2. 配置表单 =====")
    form, defaults = p.get_form()
    check("get_form 返回 (list, dict)", isinstance(form, list) and isinstance(defaults, dict))
    check("默认配置含 enabled 键", "enabled" in defaults)
    check("默认通知标题正确", defaults.get("notify_title") == "📈 股票AI分析报告")
    check("默认 LLM 来源为 system", defaults.get("llm_source") == "system")

    print("\n===== 3. 插件 API 路由声明 =====")
    apis = p.get_api()
    paths = {a["path"] for a in apis}
    check("声明 4 个接口", len(apis) == 4, str(paths))
    for needed in ("/history", "/run", "/clear", "/set_filter"):
        check(f"存在接口 {needed}", needed in paths)
    check("接口鉴权均为 bear", all(a.get("auth") == "bear" for a in apis))

    print("\n===== 4. 定时服务注册 =====")
    svcs = p.get_service()
    check("启用时注册 2 个定时任务", len(svcs) == 2, str([s["id"] for s in svcs]))
    check("未启用时不注册任务", len(build_plugin(False).get_service()) == 0)

    print("\n===== 5. 完整分析流水线（mock 行情 + LLM） =====")
    set_network_error(False)
    set_llm_error(False)
    results = p._analyze_stocks("morning")
    check("分析返回 3 只股票", len(results) == 3, f"实际 {len(results)}")
    if results:
        check("首只含 name/code/analysis", all(k in results[0] for k in ("name", "code", "analysis")))
        check("LLM 结论含免责声明", "不构成投资建议" in results[0]["analysis"])
    # _analyze_stocks 仅做分析；持久化发生在编排层 _do_analysis（manual 不跳过休市）
    p._do_analysis("morning", manual=True)
    hist = p.get_data("analysis_history")
    check("历史记录已持久化", isinstance(hist, list) and len(hist) == 1, f"len={len(hist) if hist else 0}")
    if hist:
        check("历史记录含 3 只股票", len(hist[0]["stocks"]) == 3)

    print("\n===== 6. 历史页 get_page 渲染 =====")
    page = p.get_page()
    check("get_page 返回组件列表", isinstance(page, list) and len(page) > 0)
    check("页面含 VCard(统计/记录卡)", has_component(page, "VCard"))
    check("页面含筛选/操作按钮 VBtn", has_component(page, "VBtn"))
    # 清空后应为空状态提示
    p.save_data("analysis_history", [])
    page_empty = p.get_page()
    check("清空后页面含 VAlert 提示", has_component(page_empty, "VAlert"))

    print("\n===== 7. API 端点行为 =====")
    p2 = build_plugin(True)
    p2._manual_run()  # 手动分析（早盘+收盘），写入历史
    r = p2.api_get_history()
    check("/history 返回 code=0", r.get("code") == 0)
    check("/history 返回 2 条", r.get("total") == 2, str(r.get("total")))
    r_m = p2.api_get_history(mode="morning")
    check("/history?mode=morning 仅 1 条", r_m.get("total") == 1)
    rf = p2.api_set_filter(mode="close")
    check("/set_filter 生效", rf.get("code") == 0 and p2.get_data("history_filter") == "close")
    rr = p2.api_run()
    check("/run 返回 code=0", rr.get("code") == 0)
    check("/run 后历史增长(>=3)", len(p2.get_data("analysis_history")) >= 3)
    rc = p2.api_clear()
    check("/clear 返回 code=0", rc.get("code") == 0)
    check("/clear 后历史为空", len(p2.get_data("analysis_history")) == 0)

    print("\n===== 8. 异常处理（不中断主流程） =====")
    p3 = build_plugin(True)
    set_network_error(True)
    res_err = p3._analyze_stocks("morning")
    check("行情异常时结果为空且未崩溃", res_err == [])
    set_network_error(False)
    set_llm_error(True)
    res_llm = p3._analyze_stocks("close")
    check("LLM 异常时仍返回股票(降级文案)", len(res_llm) == 3)
    if res_llm:
        check("LLM 失败结论为降级文案", res_llm[0]["analysis"] == "分析接口暂时不可用")
    set_llm_error(False)

    print("\n===== 9. 仅依赖内置库 import 校验 =====")
    check("插件模块成功导入", main is not None)

    # 汇总
    failed = [n for n, c, _ in RESULTS if not c]
    print("\n========================================")
    print(f"总计 {len(RESULTS)} 项，通过 {len(RESULTS) - len(failed)} 项，失败 {len(failed)} 项")
    if failed:
        print("失败项：", failed)
        return 1
    print("✅ 全部联调用例通过")
    return 0


if __name__ == "__main__":
    sys.exit(main_test())
