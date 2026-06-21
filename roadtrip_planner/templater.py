"""模板编排模块 - 攻略 / 测评 / 避坑三种内容口径清洗"""
from typing import List, Dict, Any
from copy import deepcopy

from .models import (
    Roadbook, DayPlan, RoadEvent, EventType, TemplateStyle
)
from .utils import format_duration


class BaseStyler:
    """模板基类"""
    style: TemplateStyle
    title_suffix: str = ""
    intro_template: str = ""

    PROMOTED_EVENT_TYPES: List[EventType] = []   # 该模板下更突出的事件类型
    SUPPRESSED_EVENT_TYPES: List[EventType] = [] # 该模板下弱化的类型

    def apply(self, rb: Roadbook) -> Roadbook:
        result = deepcopy(rb)
        result.template_style = self.style
        result.title = f"{result.title}｜{self.title_suffix}"
        for day in result.days:
            self._process_day(day)
        self._aggregate_stats(result)
        return result

    def _process_day(self, day: DayPlan) -> None:
        """处理单日：排序、过滤、补充描述、打标签"""
        day.events = sorted(day.events, key=lambda e: e.timestamp)
        self._enhance_descriptions(day)
        self._sort_by_importance(day)
        day.summary = self._build_day_summary(day)

    def _enhance_descriptions(self, day: DayPlan) -> None:
        for e in day.events:
            extras = self._build_extra_fields(e)
            if extras:
                parts = []
                if e.description:
                    parts.append(e.description)
                parts.extend(extras)
                e.description = "\n\n".join(parts)

    def _build_extra_fields(self, event: RoadEvent) -> List[str]:
        """子类重写：给某事件追加描述行"""
        return []

    def _sort_by_importance(self, day: DayPlan) -> None:
        """在保持时间顺序前提下，把重要类型的描述权重提高（通过tags、rating）"""
        for e in day.events:
            if e.event_type in self.PROMOTED_EVENT_TYPES:
                e.tags = list(dict.fromkeys(["重点"] + e.tags))
                if e.rating is None:
                    e.rating = 4
            elif e.event_type in self.SUPPRESSED_EVENT_TYPES:
                e.tags = [t for t in e.tags if t != "重点"]

    def _build_day_summary(self, day: DayPlan) -> str:
        return f"{day.title}: 行驶 {day.total_distance_km:.1f} 公里"

    def _aggregate_stats(self, rb: Roadbook) -> None:
        stats: Dict[str, Any] = {
            "total_events": sum(len(d.events) for d in rb.days),
            "key_points": self._collect_key_points(rb),
        }
        rb.meta["template_stats"] = stats

    def _collect_key_points(self, rb: Roadbook) -> List[str]:
        points = []
        for day in rb.days:
            for e in day.events:
                if e.event_type in self.PROMOTED_EVENT_TYPES:
                    if e.title not in points:
                        points.append(e.title)
        return points[:20]


class GuideStyler(BaseStyler):
    """攻略模板：突出里程油耗、拍照点位、费用"""
    style = TemplateStyle.GUIDE
    title_suffix = "实用攻略版"
    PROMOTED_EVENT_TYPES = [
        EventType.SCENIC_STOP, EventType.PHOTO, EventType.LUNCH,
        EventType.DINNER, EventType.HOTEL_CHECKIN, EventType.FUEL,
    ]
    SUPPRESSED_EVENT_TYPES = [EventType.REST, EventType.NOTE]

    def _build_extra_fields(self, event: RoadEvent) -> List[str]:
        extras = []
        if event.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM):
            lines = []
            if event.distance_km > 0:
                lines.append(f"📏 本段里程：{event.distance_km:.1f} 公里")
            if event.duration_minutes > 0:
                lines.append(f"⏱ 预计耗时：{format_duration(event.duration_minutes)}")
            if event.avg_speed is not None:
                lines.append(f"🚗 平均车速：{event.avg_speed:.0f} km/h")
            if lines:
                extras.append("【路况速览】\n" + "｜".join(lines))
            if event.cumulative_km > 0:
                extras.append(f"【累计里程】\n已行驶 {event.cumulative_km:.1f} 公里")
        if event.event_type == EventType.FUEL:
            fuel_line = []
            if event.fuel_cost > 0:
                fuel_line.append(f"⛽ 油费 ¥{event.fuel_cost:.0f}")
            if event.toll_cost > 0:
                fuel_line.append(f"🛣 过路费 ¥{event.toll_cost:.0f}")
            if fuel_line:
                extras.append("【费用】\n" + "｜".join(fuel_line))
        if event.event_type in (EventType.LUNCH, EventType.DINNER, EventType.HOTEL_CHECKIN):
            cb = event.cost_breakdown or {}
            cost_parts = []
            if event.event_type in (EventType.LUNCH, EventType.DINNER):
                if cb.get("food"):
                    cost_parts.append(f"餐费 ¥{cb['food']:.0f}")
                if cb.get("per_person"):
                    cost_parts.append(f"人均约 ¥{cb['per_person']:.0f}")
                if cb.get("ticket"):
                    cost_parts.append(f"门票 ¥{cb['ticket']:.0f}")
            else:
                if cb.get("accommodation"):
                    cost_parts.append(f"房价 ¥{cb['accommodation']:.0f}/晚")
                if cb.get("parking"):
                    cost_parts.append(f"停车费 ¥{cb['parking']:.0f}")
            if cost_parts:
                extras.append("【预算参考】\n" + "｜".join(cost_parts))
            elif event.other_cost > 0 or event.total_cost > 0:
                c = event.other_cost or event.total_cost
                name = "餐费" if event.event_type in (EventType.LUNCH, EventType.DINNER) else "住宿"
                extras.append(f"【{name}】\n💰 预计花费 ¥{c:.0f}")
        if event.event_type in (EventType.SCENIC_STOP, EventType.PHOTO):
            if event.photos:
                extras.append(f"📸 拍摄参考：{len(event.photos)} 张照片已关联")
            if event.duration_minutes > 0:
                extras.append(f"⏰ 建议停留：{format_duration(event.duration_minutes)}")
            if event.highlights:
                extras.append("✨ 亮点：" + "；".join(event.highlights[:3]))
            cb = event.cost_breakdown or {}
            if cb.get("ticket"):
                extras.append(f"🎫 门票参考：¥{cb['ticket']:.0f}")
        return extras

    def _build_day_summary(self, day: DayPlan) -> str:
        key_stops = [e.title for e in day.events
                     if e.event_type in (EventType.SCENIC_STOP, EventType.PHOTO)]
        stops = "、".join(key_stops[:3]) + (" 等" if len(key_stops) > 3 else "")
        cost = day.total_cost
        photo_n = getattr(day, "photo_count", 0)
        summary = (f"第 {day.day_index} 天｜{day.date}｜"
                   f"行驶 {day.total_distance_km:.1f}km｜耗时 {day.total_duration_hours:.1f}h｜"
                   f"当日费用约 ¥{cost:.0f}｜{photo_n} 张素材")
        if stops:
            summary += f"｜核心打卡：{stops}"
        return summary

    def _aggregate_stats(self, rb: Roadbook) -> None:
        super()._aggregate_stats(rb)
        budget_table: List[Dict[str, Any]] = []
        for d in rb.days:
            bd = getattr(d, "cost_breakdown", {}) or {}
            budget_table.append({
                "day": d.day_index,
                "date": d.date,
                "fuel": round(bd.get("fuel", 0), 2),
                "toll": round(bd.get("toll", 0), 2),
                "accommodation": round(bd.get("accommodation", 0), 2),
                "food": round(bd.get("food", 0), 2),
                "ticket": round(bd.get("ticket", 0), 2),
                "parking": round(bd.get("parking", 0), 2),
                "other": round(bd.get("other", 0), 2),
                "total": round(d.total_cost, 2),
            })
        total_bd = getattr(rb, "cost_breakdown", {}) or {}
        per_person_est = None
        all_pp = []
        for d in rb.days:
            for e in d.events:
                cb = e.cost_breakdown or {}
                if cb.get("per_person"):
                    all_pp.append(float(cb["per_person"]))
        if all_pp:
            per_person_est = round(sum(all_pp) / len(all_pp), 2)
        photo_spots_rich = []
        for spot in rb.photo_spots or []:
            ev_day = next((d for d in rb.days if d.day_index == spot.get("day")), None)
            event_ref = None
            if ev_day:
                for e in ev_day.events:
                    if e.title == spot.get("name"):
                        event_ref = e
                        break
            extra = {"tickets": None, "parking_fee": None, "stay_minutes": None}
            if event_ref:
                cb = event_ref.cost_breakdown or {}
                extra["tickets"] = cb.get("ticket")
                extra["parking_fee"] = cb.get("parking")
                extra["stay_minutes"] = event_ref.duration_minutes
            enriched = dict(spot)
            enriched.update(extra)
            photo_spots_rich.append(enriched)
        rb.meta["guide_budget_table"] = budget_table
        rb.meta["guide_budget_summary"] = {
            "grand_total": round(rb.total_cost, 2),
            "breakdown": {k: round(v, 2) for k, v in total_bd.items()},
            "per_person_avg": per_person_est,
        }
        rb.photo_spots = photo_spots_rich
        rb.cost_breakdown = {k: round(v, 2) for k, v in total_bd.items()}


class ReviewStyler(BaseStyler):
    """测评模板：突出路况、驾驶感受、设施评分、时间成本"""
    style = TemplateStyle.REVIEW
    title_suffix = "深度测评版"
    PROMOTED_EVENT_TYPES = [
        EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM,
        EventType.SCENIC_STOP, EventType.HOTEL_CHECKIN, EventType.FUEL,
    ]
    SUPPRESSED_EVENT_TYPES = [EventType.PHOTO, EventType.NOTE]

    def _build_extra_fields(self, event: RoadEvent) -> List[str]:
        extras = []
        if event.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM):
            assess = []
            if event.avg_speed is not None:
                if event.avg_speed < 20:
                    assess.append("🛑 低速区间：疑似城镇/山路/拥堵")
                elif event.avg_speed < 50:
                    assess.append("🚧 中速区间：国省道/山路为主")
                elif event.avg_speed < 90:
                    assess.append("🛣 高速区间：顺畅通行")
                else:
                    assess.append("🛫 畅通：接近限速上限")
            if event.distance_km > 0:
                assess.append(f"里程 {event.distance_km:.1f}km / 用时 {format_duration(event.duration_minutes)}")
            if assess:
                extras.append("【驾驶测评】\n" + "｜".join(assess))
            if event.road_condition_score is not None:
                stars = "★" * event.road_condition_score + "☆" * (5 - event.road_condition_score)
                extras.append(f"🛣 路况评分：{stars} ({event.road_condition_score}/5)")
            if event.driving_difficulty:
                diff_map = {"简单": "🟢 简单", "中等": "🟡 中等",
                            "困难": "🟠 困难", "地狱": "🔴 地狱"}
                extras.append(f"🏁 驾驶难度：{diff_map.get(event.driving_difficulty, event.driving_difficulty)}")
            if event.event_type == EventType.TRAFFIC_JAM:
                extras.append(
                    f"【拥堵报告】\n"
                    f"堵车约 {format_duration(event.duration_minutes)}，"
                    f"本段平均时速 {event.avg_speed or 0:.0f} km/h"
                )
                if event.pitfalls:
                    extras.append("⚠ 拥堵原因：" + "；".join(event.pitfalls))
        if event.event_type == EventType.SCENIC_STOP:
            extras.append(f"📊 设施评分：{event.rating or 4}/5")
            extras.append(f"⏱ 停留时长：{format_duration(event.duration_minutes)}")
            if event.highlights:
                extras.append("🎯 测评亮点：" + "；".join(event.highlights[:3]))
            if event.pitfalls:
                extras.append("💢 待改进：" + "；".join(event.pitfalls[:3]))
        if event.event_type == EventType.HOTEL_CHECKIN:
            extras.append(f"🏨 住宿评分：{event.rating or 4}/5")
            cb = event.cost_breakdown or {}
            price_parts = []
            if cb.get("accommodation"):
                price_parts.append(f"房费 ¥{cb['accommodation']:.0f}/晚")
            elif event.total_cost > 0:
                price_parts.append(f"房费 ¥{event.total_cost:.0f}")
            if price_parts:
                extras.append("💰 " + "｜".join(price_parts) + "（性价比评估）")
        return extras

    def _build_day_summary(self, day: DayPlan) -> str:
        road_segments = [e for e in day.events
                         if e.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM)]
        total_drive = sum(e.duration_minutes for e in road_segments)
        jams = sum(1 for e in road_segments if e.event_type == EventType.TRAFFIC_JAM)
        avg_speed = (day.total_distance_km / (total_drive / 60)) if total_drive > 0 else 0
        scores = [e.road_condition_score for e in road_segments if e.road_condition_score]
        avg_score = round(sum(scores) / len(scores), 2) if scores else None
        diff = getattr(day, "driving_difficulty_avg", None)
        summary = (f"第 {day.day_index} 天｜{day.date}｜"
                   f"里程 {day.total_distance_km:.1f}km｜纯驾驶 {format_duration(total_drive)}｜"
                   f"平均 {avg_speed:.0f}km/h｜拥堵 {jams} 段")
        if avg_score:
            summary += f"｜路况 {avg_score:.1f}/5"
        if diff:
            summary += f"｜难度{diff}"
        return summary

    def _aggregate_stats(self, rb: Roadbook) -> None:
        super()._aggregate_stats(rb)
        road_segments_all: List[Dict[str, Any]] = []
        scores = []
        diff_counter = {"简单": 0, "中等": 0, "困难": 0, "地狱": 0}
        jam_minutes = 0
        jam_count = 0
        per_day_review: Dict[int, Dict[str, Any]] = {}
        for d in rb.days:
            day_scores = []
            day_segments = []
            for e in d.events:
                if e.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM):
                    seg = {
                        "day": d.day_index,
                        "start_time": e.timestamp.strftime("%H:%M") if e.timestamp else "",
                        "title": e.title,
                        "distance_km": round(e.distance_km, 2),
                        "duration_min": e.duration_minutes,
                        "avg_speed": round(e.avg_speed, 1) if e.avg_speed else None,
                        "road_condition_score": e.road_condition_score,
                        "driving_difficulty": e.driving_difficulty,
                        "jam": e.event_type == EventType.TRAFFIC_JAM,
                        "pitfalls": e.pitfalls,
                    }
                    road_segments_all.append(seg)
                    day_segments.append(seg)
                    if e.road_condition_score:
                        scores.append(e.road_condition_score)
                        day_scores.append(e.road_condition_score)
                    if e.driving_difficulty in diff_counter:
                        diff_counter[e.driving_difficulty] += 1
                    if e.event_type == EventType.TRAFFIC_JAM:
                        jam_count += 1
                        jam_minutes += e.duration_minutes
            per_day_review[d.day_index] = {
                "segments": day_segments,
                "road_avg": round(sum(day_scores) / len(day_scores), 2) if day_scores else None,
            }
        overall_avg = round(sum(scores) / len(scores), 2) if scores else 0.0
        overall_difficulty = "简单"
        for k in ["地狱", "困难", "中等", "简单"]:
            if diff_counter.get(k, 0) > 0:
                overall_difficulty = k
                break
        cost_efficiency = None
        if rb.total_distance_km > 0 and rb.total_cost > 0:
            cost_efficiency = round(rb.total_cost / rb.total_distance_km, 2)
        by_day_list = []
        for day_idx, info in per_day_review.items():
            segs = info.get("segments") or []
            d_obj = next((d for d in rb.days if d.day_index == day_idx), None)
            day_km = sum(e.distance_km for e in (d_obj.events if d_obj else []))
            speeds = [e.avg_speed for e in (d_obj.events if d_obj else []) if e.avg_speed]
            avg_spd = round(sum(speeds) / len(speeds), 1) if speeds else 0
            jam_c = sum(1 for e in (d_obj.events if d_obj else []) if e.event_type == EventType.TRAFFIC_JAM)
            day_diff = d_obj.driving_difficulty_avg if d_obj else None
            by_day_list.append({
                "day": day_idx,
                "score": info.get("road_avg") or 0,
                "difficulty": day_diff,
                "km": round(day_km, 1),
                "avg_speed": avg_spd,
                "jam_count": jam_c,
                "segments_count": len(segs),
            })
        rb.road_scores = {
            "overall_avg": overall_avg,
            "overall_difficulty": overall_difficulty,
            "segment_count": len(road_segments_all),
            "difficulty_distribution": diff_counter,
            "traffic_jam_count": jam_count,
            "traffic_jam_minutes": jam_minutes,
            "cost_per_km": cost_efficiency,
            "by_day": by_day_list,
            "review_segments": road_segments_all,
        }
        rb.meta["review_segments"] = road_segments_all
        rb.meta["review_per_day"] = per_day_review


class PitfallsStyler(BaseStyler):
    """避坑模板：突出踩坑提醒、危险路段、避坑建议、备选方案"""
    style = TemplateStyle.PITFALLS
    title_suffix = "避坑指南版"
    PROMOTED_EVENT_TYPES = [
        EventType.TRAFFIC_JAM, EventType.FUEL, EventType.REST,
        EventType.HOTEL_CHECKIN, EventType.LUNCH, EventType.DINNER,
    ]
    SUPPRESSED_EVENT_TYPES = [EventType.PHOTO]

    def _build_extra_fields(self, event: RoadEvent) -> List[str]:
        extras = []
        if event.pitfall_categories:
            extras.append("🏷 坑分类：" + " / ".join(event.pitfall_categories))
        if event.event_type == EventType.TRAFFIC_JAM:
            suggestions = [
                "📌 避坑建议：提前查看实时路况，考虑错峰出行",
                f"⏳ 本次延误：{format_duration(event.duration_minutes)}",
            ]
            if event.pitfalls:
                suggestions.insert(0, "⚠ 踩坑记录：" + "；".join(event.pitfalls))
            extras.append("【避坑提醒】\n" + "\n".join(suggestions))
        if event.event_type in (EventType.DRIVING, EventType.DEPARTURE):
            if event.road_condition_score is not None:
                if event.road_condition_score <= 2:
                    extras.append(f"⚠ 路况警告：本段评分仅 {event.road_condition_score}/5，"
                                   f"难度 {event.driving_difficulty or '未知'}，谨慎驾驶")
            if event.avg_speed is not None and event.avg_speed < 30 and event.duration_minutes > 20:
                extras.append(
                    "⚠ 路况警告：该路段速度偏低，建议出发前确认是否有修路/塌方/管制"
                )
            elif event.distance_km > 150:
                extras.append(
                    "💡 长距离提示：建议中途预留 1-2 次休息，避免疲劳驾驶"
                )
        if event.event_type in (EventType.LUNCH, EventType.DINNER):
            food_parts = []
            cb = event.cost_breakdown or {}
            if cb.get("food"):
                food_parts.append(f"参考人均 ¥{cb['food']:.0f}")
            if cb.get("per_person"):
                food_parts.append(f"流水账人均 ¥{cb['per_person']:.0f}")
            if food_parts:
                extras.append("💰 消费参考：" + "｜".join(food_parts))
            extras.append("⚠ 避坑：尽量选择评分4分以上商家，避开景区门口拉客店")
        if event.event_type == EventType.HOTEL_CHECKIN:
            cb = event.cost_breakdown or {}
            if cb.get("accommodation"):
                extras.append(f"🏨 房价参考：¥{cb['accommodation']:.0f}/晚")
            extras.append("⚠ 住宿避坑：提前确认停车位、隔音、热水、空调，旺季务必锁单")
            if event.pitfalls:
                extras.append("踩坑反馈：" + "；".join(event.pitfalls))
        if event.event_type == EventType.FUEL:
            fuel_parts = []
            if event.fuel_cost:
                fuel_parts.append(f"油费 ¥{event.fuel_cost:.0f}")
            if event.toll_cost:
                fuel_parts.append(f"过路费 ¥{event.toll_cost:.0f}")
            if fuel_parts:
                extras.append("⛽ 费用：" + "｜".join(fuel_parts))
            extras.append("⚠ 加油避坑：偏远县城建议半箱以上再出发，不要依赖导航加油站信息")
        if event.event_type == EventType.REST:
            extras.append("💡 小提示：大服务区停留不超过20分钟，避开人流高峰")
        if event.event_type == EventType.SCENIC_STOP:
            cb = event.cost_breakdown or {}
            if cb.get("ticket"):
                extras.append(f"🎫 门票参考：¥{cb['ticket']:.0f}")
            if event.pitfalls:
                extras.append("⚠ 景点踩坑：" + "；".join(event.pitfalls))
            else:
                extras.append("✅ 安全提示：停车拉手刹，贵重物品随身带")
        return extras

    def _build_day_summary(self, day: DayPlan) -> str:
        pitfalls_count = sum(len(e.pitfalls) for e in day.events)
        jams = sum(1 for e in day.events if e.event_type == EventType.TRAFFIC_JAM)
        bd = getattr(day, "cost_breakdown", {}) or {}
        summary = (f"第 {day.day_index} 天｜{day.date}｜"
                   f"全程 {day.total_distance_km:.1f}km｜发现 {pitfalls_count} 处提醒｜"
                   f"拥堵 {jams} 段｜当日总费用 ¥{day.total_cost:.0f}")
        if bd.get("food") or bd.get("accommodation"):
            subs = []
            if bd.get("food"):
                subs.append(f"餐饮约¥{bd['food']:.0f}")
            if bd.get("accommodation"):
                subs.append(f"住宿约¥{bd['accommodation']:.0f}")
            if subs:
                summary += "｜" + " ".join(subs)
        return summary

    def _aggregate_stats(self, rb: Roadbook) -> None:
        super()._aggregate_stats(rb)
        categorized: Dict[str, List[Dict[str, Any]]] = {
            "费用坑": [], "路况坑": [], "住宿坑": [], "餐饮坑": [], "拍照坑": [], "其他坑": []
        }
        for d in rb.days:
            for e in d.events:
                for p in e.pitfalls:
                    cats = e.pitfall_categories or ["其他坑"]
                    for cat in cats:
                        categorized.setdefault(cat, []).append({
                            "day": d.day_index,
                            "time": e.timestamp.strftime("%H:%M") if e.timestamp else "",
                            "event": e.title,
                            "event_type": e.event_type.value,
                            "content": p,
                        })
        categorized_clean = {k: list({v["content"]: v for v in vs}.values())
                             for k, vs in categorized.items() if vs}
        rb.pitfalls_by_category = {
            k: [v["content"] for v in vs] for k, vs in categorized_clean.items()
        }
        rb.meta["pitfalls_rich"] = categorized_clean
        rb.meta["pitfalls_summary"] = {
            "total": sum(len(v) for v in categorized_clean.values()),
            "by_category": {k: len(v) for k, v in categorized_clean.items()},
            "by_day": {
                d.day_index: sum(len(e.pitfalls) for e in d.events) for d in rb.days
            }
        }


STYLERS = {
    TemplateStyle.GUIDE: GuideStyler,
    TemplateStyle.REVIEW: ReviewStyler,
    TemplateStyle.PITFALLS: PitfallsStyler,
}


def apply_template(roadbook: Roadbook, style: TemplateStyle) -> Roadbook:
    """根据模板类型编排路书"""
    if style not in STYLERS:
        raise ValueError(f"未知模板类型: {style}")
    styler = STYLERS[style]()
    return styler.apply(roadbook)
