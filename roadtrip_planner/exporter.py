"""多平台导出模块 - 公众号长文 / 短视频分镜 / 行程表"""
import os
import csv
import logging
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from .models import Roadbook, DayPlan, RoadEvent, EventType, TemplateStyle
from .utils import ensure_dir, format_time, format_duration

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 公众号长文提纲 (Markdown)
# ---------------------------------------------------------------------------

class WechatExporter:
    """生成适合公众号排版的 Markdown 长文提纲"""

    STYLE_INTRO = {
        TemplateStyle.GUIDE: ("实用攻略", "收藏这篇，出发前翻一翻就能用"),
        TemplateStyle.REVIEW: ("深度测评", "老司机实测，给你最真实的路况反馈"),
        TemplateStyle.PITFALLS: ("避坑指南", "看完这篇，少走冤枉路少花冤枉钱"),
    }

    def export(self, rb: Roadbook, output_dir: str) -> str:
        lines: List[str] = []
        lines.append(f"# {rb.title}")
        lines.append("")
        tagline = ""
        if rb.template_style:
            st, sub = self.STYLE_INTRO.get(rb.template_style, ("自驾路书", ""))
            tagline = f"**【{st}】** {sub}"
        lines.append(tagline)
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 🗺 行程概览")
        lines.append("")
        lines.append(f"- 📅 出行天数：{rb.total_days} 天")
        lines.append(f"- 🛣 总里程：{rb.total_distance_km:.1f} 公里")
        if rb.total_cost > 0:
            lines.append(f"- 💰 总花费：约 ¥{rb.total_cost:.0f}")
        if rb.destinations:
            lines.append(f"- 🎯 途经：{' → '.join(d.name for d in rb.destinations)}")
        lines.append("")
        lines.append("## 📋 目录")
        lines.append("")
        for day in rb.days:
            lines.append(f"- [{day.title}](#day-{day.day_index})")
        lines.append("")
        lines.append("---")
        lines.append("")
        for day in rb.days:
            lines.extend(self._render_day(day))
        lines.append("---")
        lines.append("")
        lines.append("## 🎒 写在最后")
        lines.append("")
        lines.append(
            "- 本文由 **Roadtrip Planner** 自动生成初稿，"
            "创作时请根据个人感受二次润色。"
        )
        lines.append("- 如有补充或修正，欢迎在评论区留言。")
        lines.append("")
        output_path = os.path.join(output_dir, f"{self._slug(rb.title)}_公众号长文.md")
        ensure_dir(output_dir)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return output_path

    def _render_day(self, day: DayPlan) -> List[str]:
        lines = []
        lines.append(f"## 📍 <a id=\"day-{day.day_index}\"></a>{day.title}")
        lines.append("")
        lines.append(f"> {day.summary}")
        lines.append("")
        lines.append("### 🗓 本日行程")
        lines.append("")
        lines.append("| 时间 | 事件 | 里程 | 时长 | 备注 |")
        lines.append("|------|------|------|------|------|")
        for e in day.events:
            t = format_time(e.timestamp) if e.timestamp else "--:--"
            km = f"{e.distance_km:.1f}km" if e.distance_km > 0 else "-"
            dur = format_duration(e.duration_minutes) if e.duration_minutes > 0 else "-"
            note = "📸" * min(len(e.photos), 3)
            if e.rating:
                note += f" ⭐{e.rating}"
            lines.append(f"| {t} | {self._emoji(e)}{e.title} | {km} | {dur} | {note} |")
        lines.append("")
        detail_title = "### ✏ 内容初稿（按模板重点展开）"
        lines.append(detail_title)
        lines.append("")
        for e in day.events:
            lines.extend(self._render_event_detail(e))
        lines.append("")
        return lines

    def _render_event_detail(self, e: RoadEvent) -> List[str]:
        out = []
        time_str = format_time(e.timestamp) if e.timestamp else ""
        out.append(f"#### {self._emoji(e)}{e.title}" + (f"  <small>({time_str})</small>" if time_str else ""))
        out.append("")
        if e.description:
            for para in e.description.split("\n\n"):
                para = para.strip()
                if para:
                    out.append(f"> {para}")
                    out.append("")
        bullets = []
        if e.distance_km > 0:
            bullets.append(f"里程 {e.distance_km:.1f} 公里")
        if e.duration_minutes > 0:
            bullets.append(f"用时 {format_duration(e.duration_minutes)}")
        if e.total_cost > 0:
            bullets.append(f"花费 ¥{e.total_cost:.0f}")
        if e.photos:
            bullets.append(f"{len(e.photos)} 张素材待选")
        if bullets:
            out.append("**关键信息：** " + "｜".join(bullets))
            out.append("")
        if e.highlights:
            out.append("**亮点 ✨：** " + "；".join(e.highlights))
            out.append("")
        if e.pitfalls:
            out.append("**注意 ⚠：** " + "；".join(e.pitfalls))
            out.append("")
        return out

    def _emoji(self, e: RoadEvent) -> str:
        return {
            EventType.DEPARTURE: "🚗 ",
            EventType.DRIVING: "🛣 ",
            EventType.TRAFFIC_JAM: "🚧 ",
            EventType.SCENIC_STOP: "🏞 ",
            EventType.PHOTO: "📸 ",
            EventType.LUNCH: "🍜 ",
            EventType.DINNER: "🍽 ",
            EventType.HOTEL_CHECKIN: "🏨 ",
            EventType.FUEL: "⛽ ",
            EventType.REST: "☕ ",
            EventType.NOTE: "📝 ",
            EventType.OTHER: "📍 ",
        }.get(e.event_type, "📍 ")

    def _slug(self, s: str) -> str:
        import re
        s = re.sub(r'[\\/:*?"<>|]', '_', s)
        return s.strip()[:40] or "roadtrip"


# ---------------------------------------------------------------------------
# 短视频分镜清单 (CSV)
# ---------------------------------------------------------------------------

class VideoShotlistExporter:
    """生成短视频分镜清单 CSV"""

    SHOT_TYPES = {
        EventType.DEPARTURE: [("车内", "收拾行李 / 出发口播", "第一人称视角"),
                               ("车外", "车辆启动驶出车位", "广角远景")],
        EventType.DRIVING: [("车载机位", "路面空镜 / 风光掠影", "前进视角"),
                             ("副驾机位", "驾驶员侧面镜头", "中景")],
        EventType.TRAFFIC_JAM: [("车内", "导航拥堵界面 + 表情", "近景"),
                                 ("航拍/高处", "车流长镜头", "远景")],
        EventType.SCENIC_STOP: [("车外", "人车合影 / 标志性机位", "广角"),
                                 ("手持", "景物细节特写", "近景/微距")],
        EventType.PHOTO: [("幕后", "摄影师工作瞬间", "中景"),
                           ("成品插入", "实拍画面 B-roll", "空镜")],
        EventType.LUNCH: [("桌面", "菜品全景 + 特写", "俯拍")],
        EventType.DINNER: [("环境", "餐厅环境 / 夜市烟火", "广角")],
        EventType.HOTEL_CHECKIN: [("大堂", "办理入住 / 门卡", "中景"),
                                   ("房间", "一镜到底 Room Tour", "手持")],
        EventType.FUEL: [("车外", "加油枪插入油箱口", "特写")],
        EventType.REST: [("环境", "服务区快速扫镜", "平移")],
    }

    def export(self, rb: Roadbook, output_dir: str) -> str:
        ensure_dir(output_dir)
        output_path = os.path.join(output_dir, f"{self._slug(rb.title)}_短视频分镜.csv")
        with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "分镜号", "天数", "时间", "段落", "场景", "画面内容",
                "景别/机位", "预计时长(秒)", "旁白/台词提示", "画面参考", "BGM氛围", "备注"
            ])
            shot_no = 0
            for day in rb.days:
                shot_no = self._write_opening(writer, shot_no, day)
                for e in day.events:
                    shot_no = self._write_event_shots(writer, shot_no, day, e)
                shot_no = self._write_bridge(writer, shot_no, day)
        return output_path

    def _write_opening(self, writer, shot_no, day: DayPlan) -> int:
        shot_no += 1
        writer.writerow([
            f"S{shot_no:03d}", f"Day {day.day_index}", "开场",
            "当日开篇", "车外/车内",
            f"{day.date} 开场标题卡 + 车辆点火空镜", "混合",
            "5-8", f"【旁白】第 {day.day_index} 天，{day.summary[:30]}…",
            "标题卡", "激昂 / 清新", "开头可放当日最震撼镜头做钩子"
        ])
        return shot_no

    def _write_event_shots(self, writer, shot_no, day: DayPlan, e: RoadEvent) -> int:
        shots = self.SHOT_TYPES.get(e.event_type, [("通用", e.title, "根据场景")])
        for idx, (scene, content, camera) in enumerate(shots):
            shot_no += 1
            t = format_time(e.timestamp) if e.timestamp else ""
            duration = self._suggest_duration(e, idx)
            voiceover = self._suggest_voiceover(e, idx)
            reference = ""
            if e.photos:
                reference = e.photos[0].description if idx == 0 else ""
            writer.writerow([
                f"S{shot_no:03d}", f"Day {day.day_index}", t, e.title,
                scene, content, camera, duration, voiceover, reference,
                self._suggest_bgm(e), self._extra_notes(e)
            ])
        return shot_no

    def _write_bridge(self, writer, shot_no, day: DayPlan) -> int:
        shot_no += 1
        writer.writerow([
            f"S{shot_no:03d}", f"Day {day.day_index}", "收尾",
            "当日收束", "延时/日落",
            "当日精选镜头蒙太奇 + 明日预告", "快剪",
            "10-15", "【字幕】未完待续…",
            "当日最佳片段", "温馨 / 悬念", "如为大结局则换成总结"
        ])
        return shot_no

    def _suggest_duration(self, e: RoadEvent, idx: int) -> str:
        if e.event_type in (EventType.DRIVING,):
            return "8-15" if idx == 0 else "5-8"
        if e.event_type in (EventType.SCENIC_STOP, EventType.PHOTO):
            return "10-20" if idx == 0 else "5-10"
        if e.event_type in (EventType.LUNCH, EventType.DINNER):
            return "8-12"
        if e.event_type == EventType.HOTEL_CHECKIN:
            return "15-25"
        return "5-10"

    def _suggest_voiceover(self, e: RoadEvent, idx: int) -> str:
        t = format_time(e.timestamp) if e.timestamp else ""
        if e.event_type == EventType.DEPARTURE:
            return f"【口播】{t} 出发，今天的目标是…"
        if e.event_type == EventType.TRAFFIC_JAM:
            return f"【吐槽】堵车了，{format_duration(e.duration_minutes)}原地不动…"
        if e.event_type == EventType.SCENIC_STOP:
            return f"【感叹】终于到 {e.title}，现场比照片还震撼！" if idx == 0 else "（环境音）"
        if e.event_type == EventType.LUNCH:
            return "【口播】干饭人干饭魂，尝尝当地特色"
        if e.event_type == EventType.HOTEL_CHECKIN:
            return "【口播】给大家看一下今晚落脚的地方"
        if e.highlights and idx == 0:
            return " ".join(e.highlights[:1])
        return ""

    def _suggest_bgm(self, e: RoadEvent) -> str:
        return {
            EventType.DEPARTURE: "轻快启程",
            EventType.DRIVING: "动感节奏",
            EventType.TRAFFIC_JAM: "诙谐/停顿",
            EventType.SCENIC_STOP: "大气磅礴",
            EventType.PHOTO: "轻快鼓点",
            EventType.LUNCH: "轻松治愈",
            EventType.DINNER: "市井烟火",
            EventType.HOTEL_CHECKIN: "温暖舒缓",
            EventType.FUEL: "机械节奏",
            EventType.REST: "短暂留白",
        }.get(e.event_type, "通用背景")

    def _extra_notes(self, e: RoadEvent) -> str:
        notes = []
        if len(e.photos) >= 3:
            notes.append(f"{len(e.photos)} 张照片可插入")
        if e.pitfalls:
            notes.append("可穿插踩坑提醒字幕")
        if e.rating:
            notes.append(f"⭐{e.rating} 出镜推荐")
        return "；".join(notes)

    def _slug(self, s: str) -> str:
        import re
        s = re.sub(r'[\\/:*?"<>|]', '_', s)
        return s.strip()[:40] or "roadtrip"


# ---------------------------------------------------------------------------
# 行程表 (HTML + CSV)
# ---------------------------------------------------------------------------

class ScheduleExporter:
    """生成可下载的 HTML + CSV 行程表"""

    HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
        background:#f5f6f8; color:#222; padding:20px; }}
.container {{ max-width:1100px; margin:0 auto; }}
.header {{ background:linear-gradient(135deg,#3b82f6,#8b5cf6); color:#fff;
          padding:28px 32px; border-radius:12px; margin-bottom:20px; }}
.header h1 {{ font-size:26px; margin-bottom:8px; }}
.header .sub {{ font-size:14px; opacity:.9; }}
.stats {{ display:flex; gap:16px; flex-wrap:wrap; margin-top:16px; }}
.stat {{ background:rgba(255,255,255,.18); padding:10px 16px; border-radius:8px;
         font-size:14px; }}
.section {{ background:#fff; border-radius:12px; padding:24px; margin-bottom:20px;
            box-shadow:0 1px 3px rgba(0,0,0,.06); }}
.section h2 {{ font-size:18px; margin-bottom:16px; color:#1e293b;
              padding-bottom:10px; border-bottom:2px solid #e2e8f0; }}
.day-title {{ font-size:16px; color:#3b82f6; margin:18px 0 10px;
              display:flex; align-items:center; gap:8px; }}
.day-title .chip {{ background:#3b82f6; color:#fff; font-size:12px;
                    padding:3px 10px; border-radius:999px; }}
.summary {{ background:#f8fafc; border-left:3px solid #3b82f6;
            padding:10px 14px; font-size:13px; color:#475569; margin-bottom:12px;
            border-radius:4px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th, td {{ padding:10px 12px; text-align:left; border-bottom:1px solid #e2e8f0;
          vertical-align:top; }}
th {{ background:#f1f5f9; color:#334155; font-weight:600; }}
tr:hover td {{ background:#f8fafc; }}
.tag {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px;
        margin-right:4px; }}
.tag-重点 {{ background:#fee2e2; color:#b91c1c; }}
.tag-驾驶 {{ background:#dbeafe; color:#1d4ed8; }}
.tag-拍照 {{ background:#fce7f3; color:#be185d; }}
.tag-餐饮 {{ background:#fef3c7; color:#b45309; }}
.tag-住宿 {{ background:#ddd6fe; color:#6d28d9; }}
.cost {{ color:#16a34a; font-weight:600; }}
.download {{ display:inline-block; background:#3b82f6; color:#fff;
             padding:8px 18px; border-radius:6px; text-decoration:none;
             font-size:13px; margin-right:8px; }}
.download:hover {{ background:#2563eb; }}
.footer {{ text-align:center; color:#94a3b8; font-size:12px; padding:20px; }}
@media(max-width:640px){{
    table {{ font-size:12px; }} th,td {{ padding:6px 8px; }}
    .hide-sm {{ display:none; }}
}}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>🚗 {title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="stats">
    <div class="stat">📅 {total_days} 天</div>
    <div class="stat">🛣 {total_km} km</div>
    <div class="stat">💰 约 ¥{total_cost}</div>
    <div class="stat">🎯 {destinations_count} 个目的地</div>
  </div>
</div>

<div class="section">
  <h2>📥 下载原始数据</h2>
  <a class="download" href="{csv_filename}" download>⬇ 下载 CSV 行程表</a>
  <a class="download" href="{json_filename}" download>⬇ 下载 JSON 原始数据</a>
</div>

{day_sections}

<div class="footer">由 Roadtrip Planner 生成 · {generated_at}</div>
</div>
</body>
</html>
"""

    def export(self, rb: Roadbook, output_dir: str) -> Dict[str, str]:
        ensure_dir(output_dir)
        slug = self._slug(rb.title)
        csv_path = os.path.join(output_dir, f"{slug}_行程表.csv")
        html_path = os.path.join(output_dir, f"{slug}_行程表.html")
        json_path = os.path.join(output_dir, f"{slug}_原始数据.json")

        self._export_csv(rb, csv_path)
        self._export_json(rb, json_path)
        self._export_html(rb, html_path, csv_path, json_path)
        return {"csv": csv_path, "html": html_path, "json": json_path}

    def _export_csv(self, rb: Roadbook, path: str) -> None:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "天数", "日期", "时间", "事件类型", "事件名称", "描述",
                "里程(km)", "累计里程(km)", "时长(分钟)", "平均速度(km/h)",
                "油费", "过路费", "其他费用", "总费用",
                "纬度", "经度", "照片数", "标签", "踩坑提醒", "亮点", "评分"
            ])
            for day in rb.days:
                for e in day.events:
                    writer.writerow([
                        day.day_index, day.date,
                        e.timestamp.strftime("%H:%M") if e.timestamp else "",
                        e.event_type.value, e.title,
                        e.description.replace("\n", " / "),
                        round(e.distance_km, 2), round(e.cumulative_km, 2),
                        e.duration_minutes,
                        round(e.avg_speed, 1) if e.avg_speed else "",
                        e.fuel_cost, e.toll_cost, e.other_cost, round(e.total_cost, 2),
                        e.latitude if e.latitude is not None else "",
                        e.longitude if e.longitude is not None else "",
                        len(e.photos),
                        ",".join(e.tags),
                        " | ".join(e.pitfalls),
                        " | ".join(e.highlights),
                        e.rating if e.rating else "",
                    ])

    def _export_json(self, rb: Roadbook, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(rb.to_json())

    def _export_html(self, rb: Roadbook, html_path: str,
                     csv_path: str, json_path: str) -> None:
        day_sections_parts = []
        for day in rb.days:
            rows = ""
            for e in day.events:
                t = e.timestamp.strftime("%H:%M") if e.timestamp else ""
                tags_html = "".join(self._tag_html(t) for t in (e.tags[:3] or [self._default_tag(e)]))
                km = f"{e.distance_km:.1f}" if e.distance_km > 0 else "-"
                dur = format_duration(e.duration_minutes) if e.duration_minutes > 0 else "-"
                cost = f'<span class="cost">¥{e.total_cost:.0f}</span>' if e.total_cost > 0 else "-"
                note = ""
                if e.pitfalls:
                    note += '<br>⚠ ' + '<br>⚠ '.join(e.pitfalls[:1])
                if e.highlights:
                    note += '<br>✨ ' + '<br>✨ '.join(e.highlights[:1])
                rows += f"""<tr>
                    <td>{t}</td>
                    <td>{tags_html}{e.title}</td>
                    <td class="hide-sm">{km}</td>
                    <td class="hide-sm">{dur}</td>
                    <td>{cost}</td>
                    <td class="hide-sm">{len(e.photos)} 张</td>
                    <td>{note}</td>
                </tr>"""
            day_sections_parts.append(f"""
<div class="section">
  <div class="day-title">
    <span class="chip">DAY {day.day_index}</span>
    {day.title}
  </div>
  <div class="summary">{day.summary}</div>
  <table>
    <thead><tr>
      <th>时间</th><th>事件</th><th class="hide-sm">里程</th>
      <th class="hide-sm">时长</th><th>花费</th><th class="hide-sm">照片</th><th>备注</th>
    </tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>""")

        html = self.HTML_TEMPLATE.format(
            title=rb.title,
            subtitle=("实用攻略 / 深度测评 / 避坑指南 · 行程总表"
                      if not rb.template_style else
                      {TemplateStyle.GUIDE: "面向计划出行者的实用攻略行程表",
                       TemplateStyle.REVIEW: "老司机实测的深度测评行程表",
                       TemplateStyle.PITFALLS: "收藏级避坑指南行程表"}.get(rb.template_style, "")),
            total_days=rb.total_days,
            total_km=f"{rb.total_distance_km:.1f}",
            total_cost=f"{rb.total_cost:.0f}",
            destinations_count=len(rb.destinations),
            csv_filename=os.path.basename(csv_path),
            json_filename=os.path.basename(json_path),
            day_sections="\n".join(day_sections_parts),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

    def _tag_html(self, tag: str) -> str:
        safe = tag if tag in ["重点"] else tag[:4]
        cls = tag if tag in ["重点"] else "重点" if tag == "重点" else "驾驶"
        if any(k in tag for k in ["驾驶", "行驶", "出发"]): cls = "驾驶"
        elif any(k in tag for k in ["拍照", "摄影", "景点", "观景"]): cls = "拍照"
        elif any(k in tag for k in ["午餐", "晚餐", "吃饭", "餐厅"]): cls = "餐饮"
        elif any(k in tag for k in ["住宿", "酒店", "入住"]): cls = "住宿"
        return f'<span class="tag tag-{cls}">{safe}</span>'

    def _default_tag(self, e: RoadEvent) -> str:
        if e.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM):
            return "驾驶"
        if e.event_type in (EventType.SCENIC_STOP, EventType.PHOTO):
            return "拍照"
        if e.event_type in (EventType.LUNCH, EventType.DINNER):
            return "餐饮"
        if e.event_type == EventType.HOTEL_CHECKIN:
            return "住宿"
        return "重点"

    def _slug(self, s: str) -> str:
        import re
        s = re.sub(r'[\\/:*?"<>|]', '_', s)
        return s.strip()[:40] or "roadtrip"


# ---------------------------------------------------------------------------
# 统一导出入口
# ---------------------------------------------------------------------------

FORMAT_HANDLERS = {
    "wechat": ("公众号长文提纲", lambda rb, d: [WechatExporter().export(rb, d)]),
    "video": ("短视频分镜清单", lambda rb, d: [VideoShotlistExporter().export(rb, d)]),
    "schedule": ("行程表（HTML/CSV/JSON）",
                 lambda rb, d: list(ScheduleExporter().export(rb, d).values())),
}


def export_roadbook(rb: Roadbook, formats: List[str], output_dir: str) -> Dict[str, List[str]]:
    """多格式导出统一入口"""
    ensure_dir(output_dir)
    results: Dict[str, List[str]] = {}
    for fmt in formats:
        fmt_key = fmt.strip().lower()
        if fmt_key not in FORMAT_HANDLERS:
            logger.warning(f"忽略未知导出格式: {fmt}")
            continue
        name, handler = FORMAT_HANDLERS[fmt_key]
        files = handler(rb, output_dir)
        results[name] = [os.path.abspath(f) for f in files]
    return results
