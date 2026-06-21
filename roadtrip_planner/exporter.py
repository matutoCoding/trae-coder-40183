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
        bd = getattr(rb, "cost_breakdown", {}) or {}
        if bd:
            parts = []
            if bd.get("fuel"): parts.append(f"油费¥{bd['fuel']:.0f}")
            if bd.get("toll"): parts.append(f"过路¥{bd['toll']:.0f}")
            if bd.get("accommodation"): parts.append(f"住宿¥{bd['accommodation']:.0f}")
            if bd.get("food"): parts.append(f"餐饮¥{bd['food']:.0f}")
            if bd.get("ticket"): parts.append(f"门票¥{bd['ticket']:.0f}")
            if bd.get("parking"): parts.append(f"停车¥{bd['parking']:.0f}")
            if parts:
                lines.append(f"- 💸 费用结构：{'、'.join(parts)}")
        if rb.destinations:
            lines.append(f"- 🎯 途经：{' → '.join(d.name for d in rb.destinations)}")
        lines.append("")
        lines.extend(self._render_template_featured(rb))
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

    def _render_template_featured(self, rb: Roadbook) -> List[str]:
        """攻略/测评/避坑三种模板的顶部特色板块"""
        out = []
        style = rb.template_style
        if style == TemplateStyle.GUIDE:
            bd = getattr(rb, "cost_breakdown", {}) or {}
            budget_tbl = getattr(rb.meta, "get", lambda *_: []) if isinstance(rb.meta, dict) else rb.meta
            guide_tbl = budget_tbl.get("guide_budget_table", []) if isinstance(budget_tbl, dict) else []
            out.append("## 💰 全程预算表（攻略参考）")
            out.append("")
            out.append("| 天数 | 日期 | 油费 | 过路 | 住宿 | 餐饮 | 门票 | 停车 | 其他 | 当日合计 |")
            out.append("|------|------|------|------|------|------|------|------|------|----------|")
            if guide_tbl:
                for row in guide_tbl:
                    out.append(
                        f"| D{row['day']} | {row.get('date','')} | ¥{row.get('fuel',0):.0f} | ¥{row.get('toll',0):.0f} | "
                        f"¥{row.get('accommodation',0):.0f} | ¥{row.get('food',0):.0f} | ¥{row.get('ticket',0):.0f} | "
                        f"¥{row.get('parking',0):.0f} | ¥{row.get('other',0):.0f} | **¥{row.get('total',0):.0f}** |"
                    )
            else:
                for d in rb.days:
                    dbd = getattr(d, "cost_breakdown", {}) or {}
                    out.append(
                        f"| D{d.day_index} | {d.date} | ¥{dbd.get('fuel',0):.0f} | ¥{dbd.get('toll',0):.0f} | "
                        f"¥{dbd.get('accommodation',0):.0f} | ¥{dbd.get('food',0):.0f} | ¥{dbd.get('ticket',0):.0f} | "
                        f"¥{dbd.get('parking',0):.0f} | ¥{dbd.get('other',0):.0f} | **¥{d.total_cost:.0f}** |"
                    )
            summary = bd
            out.append(f"| **合计** | — | **¥{summary.get('fuel',0):.0f}** | **¥{summary.get('toll',0):.0f}** | "
                       f"**¥{summary.get('accommodation',0):.0f}** | **¥{summary.get('food',0):.0f}** | "
                       f"**¥{summary.get('ticket',0):.0f}** | **¥{summary.get('parking',0):.0f}** | "
                       f"**¥{summary.get('other',0):.0f}** | **¥{rb.total_cost:.0f}** |")
            out.append("")
            spots = rb.photo_spots or []
            if spots:
                out.append("## 📸 拍照点位清单（S/A/B 级）")
                out.append("")
                out.append("| 等级 | 点位 | 天数 | 时间 | 素材数 | 门票参考 | 建议停留 | 拍摄提示 |")
                out.append("|------|------|------|------|--------|----------|----------|----------|")
                for sp in spots[:30]:
                    stay = f"{sp.get('stay_minutes', 0)}分钟" if sp.get("stay_minutes") else "-"
                    tkts = f"¥{sp.get('tickets'):.0f}" if sp.get("tickets") else "免费/未知"
                    tips = ""
                    if sp.get("highlights"): tips = "✨ " + "；".join(str(h) for h in sp["highlights"][:1])
                    elif sp.get("tips"): tips = "⚠ " + "；".join(str(t) for t in sp["tips"][:1])
                    out.append(
                        f"| **{sp.get('grade','B')}** | {sp.get('name','')} | D{sp.get('day',0)} | "
                        f"{sp.get('time','')} | {sp.get('photo_count',0)}张 | {tkts} | {stay} | {tips} |"
                    )
                out.append("")
        elif style == TemplateStyle.REVIEW:
            scores = rb.road_scores or {}
            out.append("## 🏁 路况总评（老司机实测）")
            out.append("")
            ov = scores.get("overall_avg", 0) or 0
            stars = "★" * int(round(ov)) + "☆" * max(0, 5 - int(round(ov)))
            out.append(f"- **整体路况评分：{stars} ({ov}/5)**")
            diff = scores.get("overall_difficulty", "未知")
            out.append(f"- **综合驾驶难度：{diff}**")
            if scores.get("segment_count"):
                out.append(f"- 共测评 {scores['segment_count']} 个驾驶段")
            ddist = scores.get("difficulty_distribution", {}) or {}
            if any(ddist.values()):
                parts = [f"{k}{v}段" for k, v in ddist.items() if v]
                out.append(f"- 难度分布：{' / '.join(parts)}")
            jc = scores.get("traffic_jam_count", 0)
            jm = scores.get("traffic_jam_minutes", 0)
            if jc:
                out.append(f"- 遭遇拥堵 {jc} 次，累计 {jm // 60}小时{jm % 60}分钟")
            cpk = scores.get("cost_per_km")
            if cpk:
                out.append(f"- 综合出行成本约 ¥{cpk}/公里（含油费+过路+食宿+门票）")
            by_day = scores.get("by_day", []) or []
            if by_day:
                out.append("")
                out.append("| 天数 | 路况均分 | 难度 | 里程 | 均速 | 拥堵 |")
                out.append("|------|----------|------|------|------|------|")
                for d in by_day:
                    rd = d.get("score", 0) if isinstance(d, dict) else d
                    verdict = "优秀" if rd >= 4.5 else ("良好" if rd >= 3.5 else ("一般" if rd >= 2.5 else ("较差" if rd >= 1.5 else "恶劣")))
                    diff = d.get("difficulty", "-") if isinstance(d, dict) else "-"
                    km_ = f"{d.get('km', 0):.0f}" if isinstance(d, dict) else "-"
                    spd = f"{d.get('avg_speed', 0):.0f}" if isinstance(d, dict) else "-"
                    jam = f"{d.get('jam_count', 0)}次" if isinstance(d, dict) else "-"
                    out.append(f"| D{d.get('day', '?')} | {rd}/5 · {verdict} | {diff} | {km_}km | {spd}km/h | {jam} |")
            segs = rb.meta.get("review_segments", []) if isinstance(rb.meta, dict) else []
            if segs:
                out.append("")
                out.append("### 🧭 分段驾驶测评摘要")
                out.append("")
                out.append("| 天数 | 时间 | 路段 | 里程 | 均速 | 路况 | 难度 |")
                out.append("|------|------|------|------|------|------|------|")
                for seg in segs[:30]:
                    rcs = seg.get("road_condition_score")
                    rd_stars = f"{rcs}/5" if rcs else "-"
                    diff = seg.get("driving_difficulty") or "-"
                    spd = f"{seg.get('avg_speed', 0)}" if seg.get("avg_speed") else "-"
                    out.append(
                        f"| D{seg.get('day',0)} | {seg.get('start_time','')} | {seg.get('title','')} | "
                        f"{seg.get('distance_km',0)}km | {spd}km/h | {rd_stars} | {diff} |"
                    )
            out.append("")
        elif style == TemplateStyle.PITFALLS:
            cats = rb.pitfalls_by_category or {}
            rich = rb.meta.get("pitfalls_rich", {}) if isinstance(rb.meta, dict) else {}
            out.append("## ⚠ 踩坑分类汇总（避坑优先看）")
            out.append("")
            if cats:
                for cat_name, items in cats.items():
                    if not items:
                        continue
                    icon = {"费用坑": "💸", "路况坑": "🛑", "住宿坑": "🏨",
                            "餐饮坑": "🍽", "拍照坑": "📷", "其他坑": "📌"}.get(cat_name, "⚠")
                    out.append(f"### {icon} {cat_name}（共 {len(items)} 条）")
                    out.append("")
                    rich_list = rich.get(cat_name, []) if isinstance(rich, dict) else []
                    for i, item in enumerate(items, start=1):
                        meta = next((r for r in rich_list if r.get("content") == item), {})
                        day_tag = f"[D{meta.get('day','?')} {meta.get('time','')}]" if meta else ""
                        ev_tag = f" · {meta.get('event','')}" if meta and meta.get("event") else ""
                        out.append(f"{i}. {day_tag}{ev_tag}  {item}")
                    out.append("")
            else:
                out.append("*（暂未识别到明显踩坑记录，建议导入更详细的流水账备注）*")
                out.append("")
            summary = rb.meta.get("pitfalls_summary", {}) if isinstance(rb.meta, dict) else {}
            per_cat = summary.get("by_category", {}) if isinstance(summary, dict) else {}
            if per_cat:
                out.append("**避坑分布：** " + " / ".join(f"{k}{v}条" for k, v in per_cat.items()))
                out.append("")
        out.append("---")
        out.append("")
        return out

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
        if e.cumulative_km > 0:
            bullets.append(f"累计 {e.cumulative_km:.1f} 公里")
        if e.total_cost > 0:
            bullets.append(f"花费 ¥{e.total_cost:.0f}")
        if e.avg_speed is not None:
            bullets.append(f"均速 {e.avg_speed:.0f}km/h")
        if e.road_condition_score is not None:
            stars = "★" * e.road_condition_score + "☆" * (5 - e.road_condition_score)
            bullets.append(f"路况 {stars}")
        if e.driving_difficulty:
            bullets.append(f"难度{e.driving_difficulty}")
        if e.photos:
            bullets.append(f"{len(e.photos)} 张素材待选")
        if bullets:
            out.append("**关键信息：** " + "｜".join(bullets))
            out.append("")
        cost_bullets = []
        if e.fuel_cost > 0:
            cost_bullets.append(f"⛽ 油费 ¥{e.fuel_cost:.0f}")
        if e.toll_cost > 0:
            cost_bullets.append(f"🛣 过路费 ¥{e.toll_cost:.0f}")
        cb = e.cost_breakdown or {}
        if cb.get("accommodation"):
            cost_bullets.append(f"🏨 住宿 ¥{cb['accommodation']:.0f}/晚")
        if cb.get("food"):
            cost_bullets.append(f"🍽 餐饮 ¥{cb['food']:.0f}")
        if cb.get("ticket"):
            cost_bullets.append(f"🎫 门票 ¥{cb['ticket']:.0f}")
        if cb.get("parking"):
            cost_bullets.append(f"🅿 停车费 ¥{cb['parking']:.0f}")
        if cb.get("per_person"):
            cost_bullets.append(f"👥 人均约 ¥{cb['per_person']:.0f}")
        if cost_bullets:
            out.append("**费用明细：** " + "｜".join(cost_bullets))
            out.append("")
        if e.highlights:
            out.append("**亮点 ✨：** " + "；".join(e.highlights))
            out.append("")
        if e.pitfall_categories:
            out.append("**🏷 坑分类：** " + " / ".join(e.pitfall_categories))
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
                "景别/机位", "预计时长(秒)", "旁白/台词提示", "画面参考", "BGM氛围",
                "累计里程", "费用提示", "路况/评分", "踩坑提醒", "拍摄重点/备注"
            ])
            shot_no = 0
            for day in rb.days:
                shot_no = self._write_opening(writer, shot_no, day, rb)
                for e in day.events:
                    shot_no = self._write_event_shots(writer, shot_no, day, e, rb)
                shot_no = self._write_bridge(writer, shot_no, day, rb)
        return output_path

    def _write_opening(self, writer, shot_no, day: DayPlan, rb: Roadbook) -> int:
        shot_no += 1
        style_extra = ""
        if rb.template_style == TemplateStyle.GUIDE:
            style_extra = f"，当日花费约 ¥{day.total_cost:.0f}"
        elif rb.template_style == TemplateStyle.REVIEW:
            diff = getattr(day, "driving_difficulty_avg", None)
            if diff:
                style_extra = f"，今日驾驶难度 {diff}"
        elif rb.template_style == TemplateStyle.PITFALLS:
            pits = sum(len(e.pitfalls) for e in day.events)
            if pits:
                style_extra = f"，今日需注意 {pits} 处坑点"
        writer.writerow([
            f"S{shot_no:03d}", f"Day {day.day_index}", "开场",
            "当日开篇", "车外/车内",
            f"{day.date} 开场标题卡 + 车辆点火空镜", "混合",
            "5-8", f"【旁白】第 {day.day_index} 天，{day.summary[:40]}…{style_extra}",
            "标题卡", "激昂 / 清新",
            "", "", "", "", "开头可放当日最震撼镜头做钩子"
        ])
        return shot_no

    def _write_event_shots(self, writer, shot_no, day: DayPlan, e: RoadEvent, rb: Roadbook) -> int:
        shots = self.SHOT_TYPES.get(e.event_type, [("通用", e.title, "根据场景")])
        for idx, (scene, content, camera) in enumerate(shots):
            shot_no += 1
            t = format_time(e.timestamp) if e.timestamp else ""
            duration = self._suggest_duration(e, idx)
            voiceover = self._suggest_voiceover(e, idx, rb)
            reference = ""
            if e.photos:
                reference = e.photos[0].description if idx == 0 else ""
            cost_hint = self._cost_hint(e)
            road_hint = self._road_hint(e)
            pit_hint = "；".join(e.pitfalls[:2]) if e.pitfalls else ""
            writer.writerow([
                f"S{shot_no:03d}", f"Day {day.day_index}", t, e.title,
                scene, content, camera, duration, voiceover, reference,
                self._suggest_bgm(e, rb),
                f"{e.cumulative_km:.1f}km" if e.cumulative_km > 0 else "",
                cost_hint, road_hint, pit_hint, self._extra_notes(e, rb)
            ])
        return shot_no

    def _write_bridge(self, writer, shot_no, day: DayPlan, rb: Roadbook) -> int:
        shot_no += 1
        style_extra = ""
        if rb.template_style == TemplateStyle.GUIDE:
            style_extra = f"，当日 ¥{day.total_cost:.0f} 攻略收好"
        elif rb.template_style == TemplateStyle.REVIEW:
            dbd = getattr(day, "cost_breakdown", {}) or {}
            if dbd.get("fuel"):
                style_extra = f"，油费约 ¥{dbd['fuel']:.0f}"
        writer.writerow([
            f"S{shot_no:03d}", f"Day {day.day_index}", "收尾",
            "当日收束", "延时/日落",
            "当日精选镜头蒙太奇 + 明日预告", "快剪",
            "10-15", f"【字幕】未完待续…{style_extra}",
            "当日最佳片段", "温馨 / 悬念",
            "", "", "", "", "如为大结局则换成总结"
        ])
        return shot_no

    @staticmethod
    def _cost_hint(e: RoadEvent) -> str:
        hints = []
        if e.fuel_cost: hints.append(f"油费¥{e.fuel_cost:.0f}")
        if e.toll_cost: hints.append(f"过路¥{e.toll_cost:.0f}")
        cb = e.cost_breakdown or {}
        if cb.get("accommodation"): hints.append(f"住宿¥{cb['accommodation']:.0f}/晚")
        if cb.get("food"): hints.append(f"餐饮¥{cb['food']:.0f}")
        if cb.get("ticket"): hints.append(f"门票¥{cb['ticket']:.0f}")
        if cb.get("per_person"): hints.append(f"人均¥{cb['per_person']:.0f}")
        return "；".join(hints)

    @staticmethod
    def _road_hint(e: RoadEvent) -> str:
        parts = []
        if e.avg_speed is not None:
            parts.append(f"均速{e.avg_speed:.0f}km/h")
        if e.road_condition_score is not None:
            parts.append(f"路况{e.road_condition_score}/5")
        if e.driving_difficulty:
            parts.append(f"难度{e.driving_difficulty}")
        return "｜".join(parts)

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

    def _suggest_voiceover(self, e: RoadEvent, idx: int, rb: Optional[Roadbook] = None) -> str:
        t = format_time(e.timestamp) if e.timestamp else ""
        style = rb.template_style if rb and rb.template_style else None
        if e.event_type == EventType.DEPARTURE:
            km_info = f"，已跑 {e.cumulative_km:.0f} 公里" if e.cumulative_km > 0 else ""
            return f"【口播】{t} 出发，今天的目标是…{km_info}"
        if e.event_type == EventType.TRAFFIC_JAM:
            return f"【吐槽】堵车了，{format_duration(e.duration_minutes)}原地不动…" + \
                   (f" ⚠" + " ".join(e.pitfalls[:1]) if e.pitfalls else "")
        if e.event_type == EventType.SCENIC_STOP:
            if style == TemplateStyle.GUIDE:
                tkts = ""
                if (e.cost_breakdown or {}).get("ticket"):
                    tkts = f"，门票 {(e.cost_breakdown or {})['ticket']:.0f}"
                return f"【攻略口播】推荐停留 {format_duration(e.duration_minutes)}{tkts}" \
                       if idx == 0 else "（环境音）"
            if style == TemplateStyle.REVIEW and e.rating:
                return f"【测评】{e.title} 打 {e.rating} 分" if idx == 0 else "（环境音）"
            return f"【感叹】终于到 {e.title}，现场比照片还震撼！" if idx == 0 else "（环境音）"
        if e.event_type in (EventType.LUNCH, EventType.DINNER):
            cb = e.cost_breakdown or {}
            if cb.get("per_person") or cb.get("food"):
                pp = cb.get("per_person") or cb.get("food") or 0
                return f"【口播】干饭人干饭魂，人均约 {pp:.0f}"
            return "【口播】干饭人干饭魂，尝尝当地特色"
        if e.event_type == EventType.HOTEL_CHECKIN:
            cb = e.cost_breakdown or {}
            if cb.get("accommodation"):
                return f"【口播】¥{cb['accommodation']:.0f}/晚，给大家看看房间"
            return "【口播】给大家看一下今晚落脚的地方"
        if style == TemplateStyle.GUIDE and e.total_cost > 0 and idx == 0:
            return f"【攻略提示】预计花费 ¥{e.total_cost:.0f}"
        if style == TemplateStyle.PITFALLS and e.pitfalls and idx == 0:
            return "【避坑】" + " ".join(e.pitfalls[:2])
        if style == TemplateStyle.REVIEW and e.road_condition_score and idx == 0 and \
                e.event_type in (EventType.DRIVING,):
            return f"【测评】路况 {e.road_condition_score}/5，难度 {e.driving_difficulty or '未知'}"
        if e.highlights and idx == 0:
            return " ".join(e.highlights[:1])
        return ""

    def _suggest_bgm(self, e: RoadEvent, rb: Optional[Roadbook] = None) -> str:
        base = {
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
        if rb and rb.template_style == TemplateStyle.PITFALLS:
            if e.event_type == EventType.TRAFFIC_JAM:
                return base + " · 加重悬疑"
            if e.pitfalls:
                return base + " · 加旁白警示"
        if rb and rb.template_style == TemplateStyle.REVIEW:
            if e.event_type in (EventType.DRIVING, EventType.DEPARTURE):
                return base + " · 硬核引擎声"
        return base

    def _extra_notes(self, e: RoadEvent, rb: Optional[Roadbook] = None) -> str:
        notes = []
        if len(e.photos) >= 3:
            notes.append(f"{len(e.photos)} 张照片可插入")
        if e.pitfalls:
            notes.append("可穿插踩坑提醒字幕")
        if e.rating:
            notes.append(f"⭐{e.rating} 出镜推荐")
        if e.driving_difficulty == "困难" or e.driving_difficulty == "地狱":
            notes.append(f"驾驶{e.driving_difficulty}，拍慢动作/紧张感")
        if rb and rb.template_style == TemplateStyle.GUIDE and e.cost_breakdown:
            cb = e.cost_breakdown or {}
            if cb.get("per_person"):
                notes.append(f"字幕：人均¥{cb['per_person']:.0f}")
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
.container {{ max-width:1200px; margin:0 auto; }}
.header {{ background:linear-gradient(135deg,#3b82f6,#8b5cf6); color:#fff;
          padding:28px 32px; border-radius:12px; margin-bottom:20px; }}
.header-guide {{ background:linear-gradient(135deg,#0ea5e9,#10b981); }}
.header-review {{ background:linear-gradient(135deg,#f97316,#ef4444); }}
.header-pitfalls {{ background:linear-gradient(135deg,#6366f1,#8b5cf6); }}
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
.budget-mini {{ display:flex; gap:12px; flex-wrap:wrap; margin-bottom:20px; }}
.budget-card {{ flex:1; min-width:130px; background:#fff; border-radius:10px; padding:14px 16px;
                box-shadow:0 1px 3px rgba(0,0,0,.06); border-top:3px solid #3b82f6; }}
.budget-card .label {{ font-size:12px; color:#64748b; margin-bottom:4px; }}
.budget-card .value {{ font-size:20px; font-weight:700; color:#1e293b; }}
.budget-card .value .unit {{ font-size:12px; color:#64748b; font-weight:400; margin-left:2px; }}
.budget-card.fuel {{ border-top-color:#f97316; }}
.budget-card.toll {{ border-top-color:#8b5cf6; }}
.budget-card.stay {{ border-top-color:#0ea5e9; }}
.budget-card.food {{ border-top-color:#f59e0b; }}
.budget-card.ticket {{ border-top-color:#10b981; }}
.budget-card.park {{ border-top-color:#6366f1; }}
.section.summary-block {{ background:#f0fdf4; border:1px solid #bbf7d0; }}
.section.review-block {{ background:#fff7ed; border:1px solid #fed7aa; }}
.section.pitfalls-block {{ background:#eef2ff; border:1px solid #c7d2fe; }}
.chips {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
.chip {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:11px;
         font-weight:500; }}
.chip-green {{ background:#dcfce7; color:#166534; }}
.chip-yellow {{ background:#fef9c3; color:#854d0e; }}
.chip-red {{ background:#fee2e2; color:#991b1b; }}
.chip-blue {{ background:#dbeafe; color:#1e40af; }}
.chip-purple {{ background:#ede9fe; color:#5b21b6; }}
.chip-orange {{ background:#ffedd5; color:#9a3412; }}
.pitfalls-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
                   gap:12px; margin-top:12px; }}
.pitfall-card {{ background:#fff; border-radius:10px; padding:14px 16px;
                  border-left:4px solid #ef4444; box-shadow:0 1px 2px rgba(0,0,0,.05); }}
.pitfall-card .phead {{ font-weight:600; font-size:13px; margin-bottom:6px; color:#991b1b; }}
.pitfall-card .plist {{ font-size:12px; color:#475569; line-height:1.7; }}
.pitfall-card.费用坑 {{ border-left-color:#ea580c; }}
.pitfall-card.路况坑 {{ border-left-color:#dc2626; }}
.pitfall-card.住宿坑 {{ border-left-color:#7c3aed; }}
.pitfall-card.餐饮坑 {{ border-left-color:#d97706; }}
.pitfall-card.拍照坑 {{ border-left-color:#db2777; }}
.pitfall-card.其他坑 {{ border-left-color:#64748b; }}
.photo-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
                gap:12px; margin-top:12px; }}
.photo-item {{ background:#fff; border-radius:10px; padding:14px;
                box-shadow:0 1px 2px rgba(0,0,0,.05); }}
.photo-item .plevel {{ font-size:11px; font-weight:700; margin-bottom:4px; }}
.photo-item .plevel.S {{ color:#dc2626; }}
.photo-item .plevel.A {{ color:#ea580c; }}
.photo-item .plevel.B {{ color:#ca8a04; }}
.photo-item .ptitle {{ font-weight:600; font-size:13px; margin-bottom:6px; }}
.photo-item .pmeta {{ font-size:11px; color:#64748b; line-height:1.6; }}
.road-stars {{ color:#f59e0b; letter-spacing:2px; font-size:13px; }}
.diff-badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px;
                font-weight:600; }}
.diff-简单 {{ background:#dcfce7; color:#166534; }}
.diff-中等 {{ background:#fef9c3; color:#854d0e; }}
.diff-困难 {{ background:#fed7aa; color:#9a3412; }}
.diff-地狱 {{ background:#fee2e2; color:#991b1b; }}
.cost-detail {{ font-size:11px; line-height:1.8; color:#334155; }}
.cost-detail .line {{ display:flex; justify-content:space-between; gap:8px; }}
.cost-detail .k {{ color:#64748b; }}
.cost-detail .v {{ font-weight:600; white-space:nowrap; }}
.download-alt {{ display:inline-block; background:#64748b; color:#fff;
                  padding:8px 18px; border-radius:6px; text-decoration:none;
                  font-size:13px; margin-right:8px; }}
.download-alt:hover {{ background:#475569; }}
@media(max-width:640px){{
    table {{ font-size:12px; }} th,td {{ padding:6px 8px; }}
    .hide-sm {{ display:none; }}
}}
</style>
</head>
<body>
<div class="container">
<div class="header {header_class}">
  <h1>🚗 {title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="stats">
    <div class="stat">📅 {total_days} 天</div>
    <div class="stat">🛣 {total_km} km</div>
    <div class="stat">💰 约 ¥{total_cost}</div>
    <div class="stat">🎯 {destinations_count} 个目的地</div>
  </div>
</div>

{budget_html}

<div class="section">
  <h2>📥 下载原始数据</h2>
  <a class="download" href="{csv_filename}" download>⬇ 下载 CSV 行程表</a>
  <a class="download-alt" href="{json_filename}" download>⬇ 下载 JSON 原始数据</a>
</div>

{featured_section}

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
                "油费(元)", "过路费(元)", "住宿费(元)", "餐饮费(元)",
                "门票(元)", "停车费(元)", "其他费用(元)", "人均参考(元)", "总费用(元)",
                "路况评分(1-5)", "驾驶难度",
                "纬度", "经度", "照片数", "标签", "坑分类", "踩坑提醒", "亮点", "评分"
            ])
            for day in rb.days:
                for e in day.events:
                    cb = e.cost_breakdown or {}
                    writer.writerow([
                        day.day_index, day.date,
                        e.timestamp.strftime("%H:%M") if e.timestamp else "",
                        e.event_type.value, e.title,
                        e.description.replace("\n", " / "),
                        round(e.distance_km, 2), round(e.cumulative_km, 2),
                        e.duration_minutes,
                        round(e.avg_speed, 1) if e.avg_speed else "",
                        e.fuel_cost, e.toll_cost,
                        cb.get("accommodation", ""),
                        cb.get("food", ""),
                        cb.get("ticket", ""),
                        cb.get("parking", ""),
                        e.other_cost,
                        cb.get("per_person", ""),
                        round(e.total_cost, 2),
                        e.road_condition_score if e.road_condition_score else "",
                        e.driving_difficulty if e.driving_difficulty else "",
                        e.latitude if e.latitude is not None else "",
                        e.longitude if e.longitude is not None else "",
                        len(e.photos),
                        ",".join(e.tags),
                        ",".join(e.pitfall_categories),
                        " | ".join(e.pitfalls),
                        " | ".join(e.highlights),
                        e.rating if e.rating else "",
                    ])

    def _export_json(self, rb: Roadbook, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(rb.to_json())

    def _export_html(self, rb: Roadbook, html_path: str,
                     csv_path: str, json_path: str) -> None:
        style = rb.template_style
        header_class = ""
        if style == TemplateStyle.GUIDE:
            header_class = "header-guide"
        elif style == TemplateStyle.REVIEW:
            header_class = "header-review"
        elif style == TemplateStyle.PITFALLS:
            header_class = "header-pitfalls"

        budget_html = self._render_budget_header(rb)
        featured_section = self._render_template_featured(rb)

        day_sections_parts = []
        for day in rb.days:
            rows = ""
            for e in day.events:
                t = e.timestamp.strftime("%H:%M") if e.timestamp else ""
                tags_html = "".join(self._tag_html(tag) for tag in (e.tags[:3] or [self._default_tag(e)]))
                seg_km = f"{e.distance_km:.1f}" if e.distance_km and e.distance_km > 0 else "-"
                cum_km = f"{e.cumulative_km:.1f}" if e.cumulative_km and e.cumulative_km > 0 else "-"
                dur = format_duration(e.duration_minutes) if e.duration_minutes and e.duration_minutes > 0 else "-"
                road_cell = self._render_road_cell(e)
                photo_cell = f"{len(e.photos)} 张" if e.photos else "-"
                cost_cell = self._render_cost_detail(e)
                note = ""
                if e.pitfalls:
                    note += '<br>⚠ ' + '<br>⚠ '.join(e.pitfalls[:1])
                if e.highlights:
                    note += '<br>✨ ' + '<br>✨ '.join(e.highlights[:1])
                if e.pitfall_categories:
                    cats = " ".join(f'<span class="chip chip-red">{c}</span>' for c in e.pitfall_categories)
                    note = cats + (f"<br>{note}" if note else "")
                rows += f"""<tr>
                    <td>{t}</td>
                    <td>{tags_html}{e.title}</td>
                    <td class="hide-sm">{seg_km}</td>
                    <td class="hide-sm">{cum_km}</td>
                    <td class="hide-sm">{dur}</td>
                    <td class="hide-sm">{road_cell}</td>
                    <td class="hide-sm">{photo_cell}</td>
                    <td>{cost_cell}</td>
                    <td>{note}</td>
                </tr>"""
            day_extra = self._render_day_extra_header(day, rb)
            day_sections_parts.append(f"""
<div class="section">
  <div class="day-title">
    <span class="chip">DAY {day.day_index}</span>
    {day.title}
  </div>
  {day_extra}
  <div class="summary">{day.summary}</div>
  <table>
    <thead><tr>
      <th>时间</th><th>事件</th><th class="hide-sm">本段里程</th>
      <th class="hide-sm">累计里程</th><th class="hide-sm">时长</th><th class="hide-sm">路况</th>
      <th class="hide-sm">照片</th><th>费用明细</th><th>备注</th>
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
            header_class=header_class,
            budget_html=budget_html,
            featured_section=featured_section,
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

    def _render_budget_header(self, rb: Roadbook) -> str:
        cb = rb.cost_breakdown or {}
        fuel = cb.get("fuel", 0) or 0
        toll = cb.get("toll", 0) or 0
        stay = cb.get("accommodation", 0) or 0
        food = cb.get("food", 0) or 0
        ticket = cb.get("ticket", 0) or 0
        park = cb.get("parking", 0) or 0
        other = cb.get("other", 0) or 0
        total = fuel + toll + stay + food + ticket + park + other
        if total <= 0:
            return ""
        cards = f"""
  <div class="budget-card fuel">
    <div class="label">⛽ 油费</div><div class="value">{fuel:.0f}<span class="unit">元</span></div>
  </div>
  <div class="budget-card toll">
    <div class="label">🛣 过路费</div><div class="value">{toll:.0f}<span class="unit">元</span></div>
  </div>
  <div class="budget-card stay">
    <div class="label">🏨 住宿</div><div class="value">{stay:.0f}<span class="unit">元</span></div>
  </div>
  <div class="budget-card food">
    <div class="label">🍽 餐饮</div><div class="value">{food:.0f}<span class="unit">元</span></div>
  </div>
  <div class="budget-card ticket">
    <div class="label">🎫 门票</div><div class="value">{ticket:.0f}<span class="unit">元</span></div>
  </div>
  <div class="budget-card park">
    <div class="label">🅿 停车</div><div class="value">{park:.0f}<span class="unit">元</span></div>
  </div>
        """
        if other and other > 0:
            cards += f"""
  <div class="budget-card">
    <div class="label">📦 其他</div><div class="value">{other:.0f}<span class="unit">元</span></div>
  </div>
            """
        return f'<div class="budget-mini">{cards}</div>'

    def _render_template_featured(self, rb: Roadbook) -> str:
        style = rb.template_style
        sections = []
        if style == TemplateStyle.GUIDE:
            spots = rb.photo_spots or []
            if spots:
                items_html = ""
                for s in spots[:12]:
                    level = s.get("level") or s.get("grade") or "B"
                    title = s.get("name") or s.get("title") or "拍照点"
                    meta_parts = []
                    tickets = s.get("tickets") or s.get("ticket") or 0
                    parking = s.get("parking_fee") or s.get("parking") or 0
                    stay = s.get("stay_minutes") or 0
                    if tickets and tickets > 0:
                        meta_parts.append(f"🎫 门票 ¥{tickets:.0f}")
                    if parking and parking > 0:
                        meta_parts.append(f"🅿 停车 ¥{parking:.0f}")
                    if stay and stay > 0:
                        hours = stay // 60
                        mins = stay % 60
                        if hours and mins:
                            meta_parts.append(f"⏱ 建议停留 {hours}小时{mins}分钟")
                        elif hours:
                            meta_parts.append(f"⏱ 建议停留 {hours}小时")
                        else:
                            meta_parts.append(f"⏱ 建议停留 {mins}分钟")
                    highlights = s.get("highlights") or []
                    if highlights:
                        h = highlights[0]
                        h_clean = h.split("#")[0].strip() if "#" in h else h.strip()
                        if len(h_clean) > 26:
                            h_clean = h_clean[:24] + "…"
                        if h_clean:
                            meta_parts.append(f"✨ {h_clean}")
                    meta = "<br>".join(meta_parts) or "—"
                    stars = "★★★" if level == "S" else ("★★☆" if level == "A" else "★☆☆")
                    items_html += f"""<div class="photo-item"><div class="plevel {level}">{stars} {level}级</div><div class="ptitle">{title}</div><div class="pmeta">{meta}</div></div>"""
                budget_table = rb.meta.get("guide_budget_table") if hasattr(rb, "meta") else None
                budget_extra = ""
                if budget_table:
                    rows = ""
                    for d in budget_table[:10]:
                        rows += f"<tr><td>DAY{d.get('day','?')}</td><td>¥{d.get('fuel',0):.0f}</td><td>¥{d.get('toll',0):.0f}</td><td>¥{d.get('accommodation',0):.0f}</td><td>¥{d.get('food',0):.0f}</td><td>¥{d.get('ticket',0):.0f}</td><td>¥{d.get('parking',0):.0f}</td><td><b>¥{d.get('total',0):.0f}</b></td></tr>"
                    budget_extra = f"""<div class="section summary-block" style="margin-top:20px"><h2>💰 每日预算明细</h2><table><thead><tr><th>天数</th><th>油费</th><th>过路</th><th>住宿</th><th>餐饮</th><th>门票</th><th>停车</th><th>合计</th></tr></thead><tbody>{rows}</tbody></table></div>"""
                sections.append(f"""<div class="section summary-block"><h2>📸 核心拍照点位清单</h2><div class="photo-grid">{items_html}</div></div>{budget_extra}""")
        elif style == TemplateStyle.REVIEW:
            rs = rb.road_scores or {}
            overall = rs.get("overall_avg")
            overall_diff = rs.get("overall_difficulty")
            dist = rs.get("difficulty_distribution") or {}
            cpk = rs.get("cost_per_km")
            by_day = rs.get("by_day") or []
            parts = []
            if overall:
                stars = "★" * int(overall) + "☆" * max(0, 5 - int(overall))
                parts.append(f'<div><span class="road-stars">{stars}</span> 整体路况 {overall:.1f}/5.0</div>')
            if overall_diff:
                badge = f'<span class="diff-badge diff-{overall_diff}">{overall_diff}</span>'
                parts.append(f"<div>🏁 驾驶难度：{badge}</div>")
            if dist:
                dist_str = " / ".join(f"{k} {v}段" for k, v in dist.items())
                parts.append(f"<div>📊 难度分布：{dist_str}</div>")
            if cpk:
                parts.append(f"<div>💸 每公里成本：约 ¥{cpk:.2f}</div>")
            top_html = "<br>".join(parts) if parts else ""
            day_rows = ""
            for d in by_day[:10]:
                s = d.get("score") or 0
                stars = "★" * int(s) + "☆" * max(0, 5 - int(s))
                diff = d.get("difficulty") or "—"
                day_rows += f"<tr><td>DAY{d.get('day','?')}</td><td><span class='road-stars'>{stars}</span> {s:.1f}</td><td><span class='diff-badge diff-{diff}'>{diff}</span></td><td>{d.get('km',0):.0f} km</td><td>{d.get('avg_speed',0):.0f} km/h</td><td>{d.get('jam_count',0)} 次</td></tr>"
            sections.append(f"""<div class="section review-block"><h2>🏁 路况测评总览</h2><div style="font-size:14px;line-height:2">{top_html}</div></div><div class="section" style="margin-top:20px"><h2>📅 分日路况评分</h2><table><thead><tr><th>天数</th><th>路况</th><th>难度</th><th>里程</th><th>均速</th><th>拥堵</th></tr></thead><tbody>{day_rows}</tbody></table></div>""")
        elif style == TemplateStyle.PITFALLS:
            rich = rb.meta.get("pitfalls_rich") if hasattr(rb, "meta") else None
            by_cat = {}
            if isinstance(rich, dict):
                # 结构: {category: [items...]}
                for cat, items in rich.items():
                    for item in items:
                        enriched = dict(item)
                        if "category" not in enriched:
                            enriched["category"] = cat
                        by_cat.setdefault(cat, []).append(enriched)
            elif isinstance(rich, list):
                # 结构: [{category, ...}...]
                for item in rich:
                    cat = item.get("category") or "其他坑"
                    by_cat.setdefault(cat, []).append(item)
            cats_order = ["费用坑", "路况坑", "住宿坑", "餐饮坑", "拍照坑", "其他坑"]
            src_list = [i for items in by_cat.values() for i in items]
            if by_cat:
                cards = ""
                for cat in cats_order:
                    items = by_cat.get(cat, [])
                    if not items:
                        continue
                    plist = ""
                    for p in items[:6]:
                        day_tag = f"DAY{p.get('day')} " if p.get("day") else ""
                        time_tag = f"{p.get('time')} " if p.get("time") else ""
                        event_tag = f"【{p.get('event')}】" if p.get("event") else ""
                        text = p.get("text") or ""
                        plist += f"<div>• {day_tag}{time_tag}{event_tag}{text}</div>"
                    cards += f'<div class="pitfall-card {cat}"><div class="phead">⚠ {cat}（{len(items)}条）</div><div class="plist">{plist}</div></div>'
                summary = rb.meta.get("pitfalls_summary") if hasattr(rb, "meta") else None
                extra = ""
                if summary:
                    total = summary.get("total", 0)
                    by_cat_sum = summary.get("by_category") or {}
                    cats = " / ".join(f"{k}{v}条" for k, v in by_cat_sum.items())
                    extra = f'<div style="margin-bottom:12px;font-size:13px;color:#475569">全程共 <b>{total}</b> 处踩坑提醒 · {cats}</div>'
                sections.append(f"""<div class="section pitfalls-block"><h2>⚠️ 分类踩坑指南</h2>{extra}<div class="pitfalls-grid">{cards}</div></div>""")
        return "\n".join(sections)

    def _render_day_extra_header(self, day, rb: Roadbook) -> str:
        cb = day.cost_breakdown or {}
        day_total = sum(cb.values()) if cb else 0
        parts = []
        if day_total and day_total > 0:
            parts.append(f'<span class="chip chip-green">💰 当日 ¥{day_total:.0f}</span>')
        style = rb.template_style
        if style == TemplateStyle.GUIDE:
            if day.photo_count:
                parts.append(f'<span class="chip chip-blue">📸 {day.photo_count} 张拍照素材</span>')
        elif style == TemplateStyle.REVIEW:
            diff = day.driving_difficulty_avg
            if diff:
                parts.append(f'<span class="chip chip-orange">🏁 难度 {diff}</span>')
        elif style == TemplateStyle.PITFALLS:
            pits = sum(1 for e in day.events if e.pitfalls)
            if pits:
                parts.append(f'<span class="chip chip-red">⚠ {pits} 处踩坑提醒</span>')
        if not parts:
            return ""
        return f'<div class="chips">{"".join(parts)}</div>'

    @staticmethod
    def _render_cost_detail(e) -> str:
        cb = e.cost_breakdown or {}
        items = []
        if e.fuel_cost and e.fuel_cost > 0:
            items.append(("⛽ 油费", f"{e.fuel_cost:.0f}"))
        if e.toll_cost and e.toll_cost > 0:
            items.append(("🛣 过路", f"{e.toll_cost:.0f}"))
        if cb.get("accommodation"):
            items.append(("🏨 住宿", f"{cb['accommodation']:.0f}"))
        if cb.get("food"):
            items.append(("🍽 餐饮", f"{cb['food']:.0f}"))
        if cb.get("ticket"):
            items.append(("🎫 门票", f"{cb['ticket']:.0f}"))
        if cb.get("parking"):
            items.append(("🅿 停车", f"{cb['parking']:.0f}"))
        if e.other_cost and e.other_cost > 0:
            items.append(("📦 其他", f"{e.other_cost:.0f}"))
        if not items:
            return "-"
        lines = "".join(f'<div class="line"><span class="k">{k}</span><span class="v">¥{v}</span></div>' for k, v in items)
        total = e.total_cost or 0
        if total and total > 0:
            lines += f'<div class="line" style="border-top:1px dashed #e2e8f0;padding-top:3px;margin-top:3px"><span class="k"><b>合计</b></span><span class="v" style="color:#16a34a">¥{total:.0f}</span></div>'
        if cb.get("per_person"):
            lines += f'<div class="line"><span class="k">👥 人均</span><span class="v">¥{cb["per_person"]:.0f}</span></div>'
        return f'<div class="cost-detail">{lines}</div>'

    @staticmethod
    def _render_road_cell(e) -> str:
        parts = []
        if e.road_condition_score:
            s = int(e.road_condition_score)
            stars = "★" * s + "☆" * max(0, 5 - s)
            parts.append(f'<span class="road-stars">{stars}</span>')
        if e.driving_difficulty:
            d = e.driving_difficulty
            parts.append(f'<span class="diff-badge diff-{d}">{d}</span>')
        if e.avg_speed and e.avg_speed > 0:
            parts.append(f'<span style="font-size:11px;color:#64748b">{e.avg_speed:.0f}km/h</span>')
        return " ".join(parts) or "-"

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
