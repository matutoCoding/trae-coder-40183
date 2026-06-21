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
            if event.other_cost > 0 or event.total_cost > 0:
                c = event.other_cost or event.total_cost
                name = "餐费" if event.event_type in (EventType.LUNCH, EventType.DINNER) else "住宿"
                extras.append(f"【{name}】\n💰 预计花费 ¥{c:.0f}/人")
        if event.event_type in (EventType.SCENIC_STOP, EventType.PHOTO):
            if event.photos:
                extras.append(f"📸 拍摄参考：{len(event.photos)} 张照片已关联")
            if event.duration_minutes > 0:
                extras.append(f"⏰ 建议停留：{format_duration(event.duration_minutes)}")
            if event.highlights:
                extras.append("✨ 亮点：" + "；".join(event.highlights[:3]))
        return extras

    def _build_day_summary(self, day: DayPlan) -> str:
        key_stops = [e.title for e in day.events
                     if e.event_type in (EventType.SCENIC_STOP, EventType.PHOTO)]
        stops = "、".join(key_stops[:3]) + (" 等" if len(key_stops) > 3 else "")
        cost = day.total_cost
        summary = (f"第 {day.day_index} 天｜{day.date}｜"
                   f"行驶 {day.total_distance_km:.1f}km｜耗时 {day.total_duration_hours:.1f}h｜"
                   f"当日费用约 ¥{cost:.0f}")
        if stops:
            summary += f"｜核心打卡：{stops}"
        return summary


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
            if event.total_cost > 0:
                extras.append(f"💰 房费 ¥{event.total_cost:.0f}（性价比评估）")
        return extras

    def _build_day_summary(self, day: DayPlan) -> str:
        road_segments = [e for e in day.events
                         if e.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM)]
        total_drive = sum(e.duration_minutes for e in road_segments)
        jams = sum(1 for e in road_segments if e.event_type == EventType.TRAFFIC_JAM)
        avg_speed = (day.total_distance_km / (total_drive / 60)) if total_drive > 0 else 0
        summary = (f"第 {day.day_index} 天｜{day.date}｜"
                   f"里程 {day.total_distance_km:.1f}km｜纯驾驶 {format_duration(total_drive)}｜"
                   f"平均 {avg_speed:.0f}km/h｜拥堵 {jams} 段")
        return summary


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
        if event.event_type == EventType.TRAFFIC_JAM:
            suggestions = [
                "📌 避坑建议：提前查看实时路况，考虑错峰出行",
                f"⏳ 本次延误：{format_duration(event.duration_minutes)}",
            ]
            if event.pitfalls:
                suggestions.insert(0, "⚠ 踩坑记录：" + "；".join(event.pitfalls))
            extras.append("【避坑提醒】\n" + "\n".join(suggestions))
        if event.event_type in (EventType.DRIVING, EventType.DEPARTURE):
            if event.avg_speed is not None and event.avg_speed < 30 and event.duration_minutes > 20:
                extras.append(
                    "⚠ 路况警告：该路段速度偏低，建议出发前确认是否有修路/塌方/管制"
                )
            elif event.distance_km > 150:
                extras.append(
                    "💡 长距离提示：建议中途预留 1-2 次休息，避免疲劳驾驶"
                )
        if event.event_type in (EventType.LUNCH, EventType.DINNER):
            extras.append("⚠ 避坑：尽量选择评分4分以上商家，避开景区门口拉客店")
        if event.event_type == EventType.HOTEL_CHECKIN:
            extras.append("⚠ 住宿避坑：提前确认停车位、隔音、热水、空调，旺季务必锁单")
            if event.pitfalls:
                extras.append("踩坑反馈：" + "；".join(event.pitfalls))
        if event.event_type == EventType.FUEL:
            extras.append("⚠ 加油避坑：偏远县城建议半箱以上再出发，不要依赖导航加油站信息")
        if event.event_type == EventType.REST:
            extras.append("💡 小提示：大服务区停留不超过20分钟，避开人流高峰")
        if event.event_type == EventType.SCENIC_STOP:
            if event.pitfalls:
                extras.append("⚠ 景点踩坑：" + "；".join(event.pitfalls))
            else:
                extras.append("✅ 安全提示：停车拉手刹，贵重物品随身带")
        return extras

    def _build_day_summary(self, day: DayPlan) -> str:
        pitfalls_count = sum(len(e.pitfalls) for e in day.events)
        jams = sum(1 for e in day.events if e.event_type == EventType.TRAFFIC_JAM)
        summary = (f"第 {day.day_index} 天｜{day.date}｜"
                   f"全程 {day.total_distance_km:.1f}km｜发现 {pitfalls_count} 处提醒｜"
                   f"拥堵 {jams} 段｜当日总费用 ¥{day.total_cost:.0f}")
        return summary

    def _aggregate_stats(self, rb: Roadbook) -> None:
        super()._aggregate_stats(rb)
        all_pitfalls = []
        for day in rb.days:
            for e in day.events:
                all_pitfalls.extend(e.pitfalls)
        rb.meta["all_pitfalls"] = all_pitfalls


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
