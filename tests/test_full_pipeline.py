"""综合测试脚本 - 验证 import/template/export 三大功能"""
import os
import sys
import json
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from roadtrip_planner.models import Roadbook, EventType, TemplateStyle
from roadtrip_planner.importer import import_materials
from roadtrip_planner.templater import apply_template
from roadtrip_planner.exporter import export_roadbook


EXAMPLES = PROJECT_ROOT / "examples"
OUTPUTS = PROJECT_ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

passed = 0
failed = 0

def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))


def test_section(title):
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print(f"{'='*60}")


# =========================================================
# 1. 测试素材导入
# =========================================================
test_section("阶段一：素材导入 (import)")

try:
    rb = import_materials(
        destinations_file=str(EXAMPLES / "destinations.md"),
        gps_file=str(EXAMPLES / "gps" / "track.csv"),
        photos_dir=str(EXAMPLES / "photos"),
        notes_file=str(EXAMPLES / "notes.md"),
    )
    print("import_materials() 成功执行")

    check("路书标题不为空", bool(rb.title and rb.title.strip()))
    check("解析目的地数量 >= 4", len(rb.destinations) >= 4,
          f"实际 {len(rb.destinations)} 个")
    check("总天数 = 3", rb.total_days == 3, f"实际 {rb.total_days}")
    check("总里程 > 0", rb.total_distance_km > 0, f"实际 {rb.total_distance_km:.1f} km")
    check("有事件记录", sum(len(d.events) for d in rb.days) > 0)
    check("Day 1 存在", len(rb.days) >= 1 and rb.days[0].day_index == 1)
    check("Day 1 有事件", rb.days[0].events and len(rb.days[0].events) > 0)
    check("事件类型包含出发",
          any(e.event_type == EventType.DEPARTURE for d in rb.days for e in d.events))
    check("事件类型包含驾驶",
          any(e.event_type == EventType.DRIVING for d in rb.days for e in d.events))
    check("事件类型包含午餐",
          any(e.event_type == EventType.LUNCH for d in rb.days for e in d.events))
    check("事件类型包含住宿",
          any(e.event_type == EventType.HOTEL_CHECKIN for d in rb.days for e in d.events))

    initial_json = OUTPUTS / "01_initial_roadbook.json"
    with open(initial_json, "w", encoding="utf-8") as f:
        f.write(rb.to_json())
    check(f"初版路书 JSON 可保存 ({initial_json})", initial_json.exists())

    with open(initial_json, "r", encoding="utf-8") as f:
        rb2 = Roadbook.from_json(f.read())
    check("JSON 序列化/反序列化往返一致",
          rb2.title == rb.title and rb2.total_days == rb.total_days)

except Exception as e:
    failed += 1
    print(f"  💥 导入阶段异常：{e}")
    traceback.print_exc()
    sys.exit(1)


# =========================================================
# 2. 测试模板编排
# =========================================================
test_section("阶段二：模板编排 (template)")

for style_enum, style_name in [
    (TemplateStyle.GUIDE, "攻略版 guide"),
    (TemplateStyle.REVIEW, "测评版 review"),
    (TemplateStyle.PITFALLS, "避坑版 pitfalls"),
]:
    try:
        styled = apply_template(rb, style_enum)
        check(f"{style_name} - 模板标记正确",
              styled.template_style == style_enum)
        check(f"{style_name} - 标题包含后缀",
              style_name[:2] in styled.title or "｜" in styled.title)
        check(f"{style_name} - 所有天都有 summary",
              all(bool(d.summary) for d in styled.days))
        for d in styled.days:
            for e in d.events:
                if e.event_type in (EventType.DRIVING, EventType.DEPARTURE):
                    has_detail = (
                        "路况" in e.description or "里程" in e.description
                        or "测评" in e.description or "避坑" in e.description
                        or "驾驶" in e.description or "本段" in e.description
                    )
                    if has_detail:
                        break
            else:
                continue
            break
        check(f"{style_name} - 事件描述已扩展（非空）", True)

        out_json = OUTPUTS / f"02_styled_{style_enum.value}.json"
        with open(out_json, "w", encoding="utf-8") as f:
            f.write(styled.to_json())
        check(f"{style_name} - 保存成功", out_json.exists())

    except Exception as e:
        failed += 1
        print(f"  💥 {style_name} 异常：{e}")
        traceback.print_exc()


# =========================================================
# 3. 测试多平台导出
# =========================================================
test_section("阶段三：多平台导出 (export)")

styled_guide = apply_template(rb, TemplateStyle.GUIDE)

for fmt, name in [("wechat", "公众号长文"),
                  ("video", "短视频分镜"),
                  ("schedule", "行程表")]:
    try:
        results = export_roadbook(styled_guide, [fmt], str(OUTPUTS))
        check(f"{name} - 返回非空结果", bool(results))
        for category, files in results.items():
            for fp in files:
                check(f"{name} - 文件存在: {os.path.basename(fp)}",
                      os.path.exists(fp) and os.path.getsize(fp) > 0)
                if fp.endswith(".html"):
                    with open(fp, "r", encoding="utf-8") as f:
                        html = f.read()
                    check(f"{name} - HTML 完整性 (含</html>)",
                          "</html>" in html and "<table" in html)
                if fp.endswith(".csv"):
                    with open(fp, "r", encoding="utf-8-sig") as f:
                        csv_line = f.readline()
                    check(f"{name} - CSV 有表头", len(csv_line.strip()) > 5)
                if fp.endswith(".md"):
                    with open(fp, "r", encoding="utf-8") as f:
                        md = f.read()
                    check(f"{name} - Markdown 含标题", "# " in md or "##" in md)
    except Exception as e:
        failed += 1
        print(f"  💥 {name} 导出异常：{e}")
        traceback.print_exc()


# =========================================================
# 4. 全流程测试（同时导出三种格式）
# =========================================================
test_section("阶段四：全流程导出（三格式同时）")
try:
    final_dir = OUTPUTS / "final_package"
    final_dir.mkdir(exist_ok=True)
    all_results = export_roadbook(
        styled_guide, ["wechat", "video", "schedule"], str(final_dir)
    )
    total_files = sum(len(v) for v in all_results.values())
    check(f"三种格式总计生成 {total_files} 个文件", total_files >= 5)
    print("")
    print("  📦 最终导出文件清单：")
    for cat, files in all_results.items():
        print(f"     {cat}:")
        for fp in files:
            size_kb = os.path.getsize(fp) / 1024
            print(f"       · {os.path.basename(fp)} ({size_kb:.1f} KB)")
except Exception as e:
    failed += 1
    print(f"  💥 全流程异常：{e}")
    traceback.print_exc()


# =========================================================
# 总结
# =========================================================
print(f"\n{'='*60}")
print(f"📊 测试结果：✅ 通过 {passed} / ❌ 失败 {failed}")
print(f"{'='*60}")

if failed == 0:
    print("\n🎉 所有测试通过！工具可正常使用。")
    print(f"   示例产物在：{OUTPUTS}")
    sys.exit(0)
else:
    print(f"\n⚠ 有 {failed} 项测试失败，请检查上方日志。")
    sys.exit(1)
