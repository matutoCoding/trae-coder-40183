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
    photos: List[Photo] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    pitfalls: List[str] = field(default_factory=list)   # 踩坑提醒
    highlights: List[str] = field(default_factory=list)  # 亮点
    rating: Optional[int] = None       # 评分 1-5

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
            "photos": [p.to_dict() for p in self.photos],
            "tags": self.tags,
            "pitfalls": self.pitfalls,
            "highlights": self.highlights,
            "rating": self.rating,
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
    weather: str = ""

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
            "weather": self.weather,
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
    destinations: List[Destination]
    days: List[DayPlan]
    template_style: Optional[TemplateStyle] = None
    vehicle_info: Dict[str, Any] = field(default_factory=dict)
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
            "destinations": [d.to_dict() for d in self.destinations],
            "days": [d.to_dict() for d in self.days],
            "template_style": self.template_style.value if self.template_style else None,
            "vehicle_info": self.vehicle_info,
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
                    photos=photos,
                    tags=evt_data.get("tags", []),
                    pitfalls=evt_data.get("pitfalls", []),
                    highlights=evt_data.get("highlights", []),
                    rating=evt_data.get("rating"),
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
                weather=day_data.get("weather", ""),
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
            destinations=destinations,
            days=days,
            template_style=TemplateStyle(data["template_style"]) if data.get("template_style") else None,
            vehicle_info=data.get("vehicle_info", {}),
            meta=data.get("meta", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "Roadbook":
        return cls.from_dict(json.loads(json_str))
