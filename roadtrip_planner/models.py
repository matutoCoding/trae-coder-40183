"""数据模型定义"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import json


class EventType(str, Enum):
    DEPARTURE = "departure"          # 早晨出发
    SCENIC_STOP = "scenic_stop"      # 观景台/景点停留
    LUNCH = "lunch"                  # 午餐
    DINNER = "dinner"                # 晚餐
    TRAFFIC_JAM = "traffic_jam"      # 堵车
    DRIVING = "driving"              # 正常行驶
    FUEL = "fuel"                    # 加油
    REST = "rest"                    # 休息
    HOTEL_CHECKIN = "hotel_checkin"  # 住宿入住
    PHOTO = "photo"                  # 拍照点
    NOTE = "note"                    # 文字备注
    OTHER = "other"                  # 其他


class TemplateStyle(str, Enum):
    GUIDE = "guide"          # 攻略
    REVIEW = "review"        # 测评
    PITFALLS = "pitfalls"    # 避坑


@dataclass
class Waypoint:
    """GPS 轨迹点"""
    timestamp: datetime
    latitude: float
    longitude: float
    elevation: Optional[float] = None
    speed: Optional[float] = None  # km/h

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return d


@dataclass
class Photo:
    """照片信息"""
    file_path: str
    timestamp: Optional[datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return d


@dataclass
class Destination:
    """目的地信息"""
    name: str
    description: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Note:
    """文字备注"""
    timestamp: Optional[datetime]
    content: str
    tags: List[str] = field(default_factory=list)
    location: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return d


@dataclass
class RoadEvent:
    """路书中的单个事件"""
    event_id: str
    timestamp: datetime
    event_type: EventType
    title: str
    description: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    duration_minutes: int = 0          # 持续时间（分钟）
    distance_km: float = 0.0           # 本段距离（公里）
    cumulative_km: float = 0.0         # 累计里程
    avg_speed: Optional[float] = None  # 平均速度 km/h
    fuel_cost: float = 0.0             # 油费
    toll_cost: float = 0.0             # 过路费
    other_cost: float = 0.0            # 其他费用
    cost_breakdown: Dict[str, Any] = field(default_factory=dict)  # 费用明细: accommodation/food/ticket/parking/other/per_person
    photos: List[Photo] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    pitfalls: List[str] = field(default_factory=list)   # 踩坑提醒
    pitfall_categories: List[str] = field(default_factory=list)  # 坑分类（费用坑/路况坑...）
    highlights: List[str] = field(default_factory=list)  # 亮点
    rating: Optional[int] = None       # 综合评分 1-5
    road_condition_score: Optional[int] = None  # 路况评分 1-5 (测评版)
    driving_difficulty: Optional[str] = None    # 驾驶难度: 简单/中等/困难/地狱

    @property
    def total_cost(self) -> float:
        return self.fuel_cost + self.toll_cost + self.other_cost

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type.value,
            "title": self.title,
            "description": self.description,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "duration_minutes": self.duration_minutes,
            "distance_km": self.distance_km,
            "cumulative_km": self.cumulative_km,
            "avg_speed": self.avg_speed,
            "fuel_cost": self.fuel_cost,
            "toll_cost": self.toll_cost,
            "other_cost": self.other_cost,
            "total_cost": self.total_cost,
            "cost_breakdown": self.cost_breakdown,
            "photos": [p.to_dict() for p in self.photos],
            "tags": self.tags,
            "pitfalls": self.pitfalls,
            "pitfall_categories": self.pitfall_categories,
            "highlights": self.highlights,
            "rating": self.rating,
            "road_condition_score": self.road_condition_score,
            "driving_difficulty": self.driving_difficulty,
        }
        return d


@dataclass
class DayPlan:
    """单日行程"""
    day_index: int
    date: str
    title: str
    summary: str = ""
    events: List[RoadEvent] = field(default_factory=list)
    start_location: str = ""
    end_location: str = ""
    total_distance_km: float = 0.0
    total_duration_hours: float = 0.0
    total_cost: float = 0.0
    cost_breakdown: Dict[str, float] = field(default_factory=dict)  # fuel/toll/accommodation/food/ticket/parking/other
    weather: str = ""
    photo_count: int = 0
    driving_difficulty_avg: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day_index": self.day_index,
            "date": self.date,
            "title": self.title,
            "summary": self.summary,
            "events": [e.to_dict() for e in self.events],
            "start_location": self.start_location,
            "end_location": self.end_location,
            "total_distance_km": self.total_distance_km,
            "total_duration_hours": self.total_duration_hours,
            "total_cost": self.total_cost,
            "cost_breakdown": self.cost_breakdown,
            "weather": self.weather,
            "photo_count": self.photo_count,
            "driving_difficulty_avg": self.driving_difficulty_avg,
        }


@dataclass
class Roadbook:
    """完整路书"""
    title: str
    created_at: datetime
    start_date: str
    end_date: str
    total_days: int
    total_distance_km: float
    total_cost: float
    cost_breakdown: Dict[str, float] = field(default_factory=dict)  # 全程费用明细
    destinations: List[Destination] = field(default_factory=list)
    days: List[DayPlan] = field(default_factory=list)
    template_style: Optional[TemplateStyle] = None
    vehicle_info: Dict[str, Any] = field(default_factory=dict)
    photo_spots: List[Dict[str, Any]] = field(default_factory=list)  # 拍照点清单（攻略版用）
    pitfalls_by_category: Dict[str, List[str]] = field(default_factory=dict)  # 分类踩坑清单
    road_scores: Dict[str, Any] = field(default_factory=dict)  # 路况测评汇总
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_days": self.total_days,
            "total_distance_km": self.total_distance_km,
            "total_cost": self.total_cost,
            "cost_breakdown": self.cost_breakdown,
            "destinations": [d.to_dict() for d in self.destinations],
            "days": [d.to_dict() for d in self.days],
            "template_style": self.template_style.value if self.template_style else None,
            "vehicle_info": self.vehicle_info,
            "photo_spots": self.photo_spots,
            "pitfalls_by_category": self.pitfalls_by_category,
            "road_scores": self.road_scores,
            "meta": self.meta,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Roadbook":
        destinations = [
            Destination(
                name=d["name"],
                description=d.get("description", ""),
                latitude=d.get("latitude"),
                longitude=d.get("longitude"),
                order=d.get("order", 0),
            )
            for d in data.get("destinations", [])
        ]
        days = []
        for day_data in data.get("days", []):
            events = []
            for evt_data in day_data.get("events", []):
                photos = [
                    Photo(
                        file_path=p["file_path"],
                        timestamp=datetime.fromisoformat(p["timestamp"]) if p.get("timestamp") else None,
                        latitude=p.get("latitude"),
                        longitude=p.get("longitude"),
                        description=p.get("description", ""),
                    )
                    for p in evt_data.get("photos", [])
                ]
                evt = RoadEvent(
                    event_id=evt_data["event_id"],
                    timestamp=datetime.fromisoformat(evt_data["timestamp"]) if evt_data.get("timestamp") else datetime.now(),
                    event_type=EventType(evt_data["event_type"]),
                    title=evt_data["title"],
                    description=evt_data.get("description", ""),
                    latitude=evt_data.get("latitude"),
                    longitude=evt_data.get("longitude"),
                    duration_minutes=evt_data.get("duration_minutes", 0),
                    distance_km=evt_data.get("distance_km", 0.0),
                    cumulative_km=evt_data.get("cumulative_km", 0.0),
                    avg_speed=evt_data.get("avg_speed"),
                    fuel_cost=evt_data.get("fuel_cost", 0.0),
                    toll_cost=evt_data.get("toll_cost", 0.0),
                    other_cost=evt_data.get("other_cost", 0.0),
                    cost_breakdown=evt_data.get("cost_breakdown", {}),
                    photos=photos,
                    tags=evt_data.get("tags", []),
                    pitfalls=evt_data.get("pitfalls", []),
                    pitfall_categories=evt_data.get("pitfall_categories", []),
                    highlights=evt_data.get("highlights", []),
                    rating=evt_data.get("rating"),
                    road_condition_score=evt_data.get("road_condition_score"),
                    driving_difficulty=evt_data.get("driving_difficulty"),
                )
                events.append(evt)
            day = DayPlan(
                day_index=day_data["day_index"],
                date=day_data["date"],
                title=day_data["title"],
                summary=day_data.get("summary", ""),
                events=events,
                start_location=day_data.get("start_location", ""),
                end_location=day_data.get("end_location", ""),
                total_distance_km=day_data.get("total_distance_km", 0.0),
                total_duration_hours=day_data.get("total_duration_hours", 0.0),
                total_cost=day_data.get("total_cost", 0.0),
                cost_breakdown=day_data.get("cost_breakdown", {}),
                weather=day_data.get("weather", ""),
                photo_count=day_data.get("photo_count", 0),
                driving_difficulty_avg=day_data.get("driving_difficulty_avg"),
            )
            days.append(day)
        return cls(
            title=data["title"],
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            start_date=data.get("start_date", ""),
            end_date=data.get("end_date", ""),
            total_days=data.get("total_days", 0),
            total_distance_km=data.get("total_distance_km", 0.0),
            total_cost=data.get("total_cost", 0.0),
            cost_breakdown=data.get("cost_breakdown", {}),
            destinations=destinations,
            days=days,
            template_style=TemplateStyle(data["template_style"]) if data.get("template_style") else None,
            vehicle_info=data.get("vehicle_info", {}),
            photo_spots=data.get("photo_spots", []),
            pitfalls_by_category=data.get("pitfalls_by_category", {}),
            road_scores=data.get("road_scores", {}),
            meta=data.get("meta", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Roadbook":
        return cls.from_dict(json.loads(json_str))
