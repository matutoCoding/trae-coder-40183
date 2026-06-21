"""素材导入模块 - GPS解析、照片EXIF、文件读取、事件归类"""
import os
import re
import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple, Any
from pathlib import Path

from .models import (
    Waypoint, Photo, Destination, Note, RoadEvent, DayPlan, Roadbook, EventType
)
from .utils import (
    haversine_distance, parse_datetime, generate_event_id, classify_time_of_day,
    extract_tags_from_text, clean_text,
    extract_costs, cost_breakdown_to_fields,
    build_mileage_timeline, lookup_cumulative_mileage,
    categorize_pitfall, ensure_dir, save_json
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GPS 轨迹解析
# ---------------------------------------------------------------------------

class GPXParser:
    """GPX 文件解析器"""

    @staticmethod
    def parse(file_path: str) -> List[Waypoint]:
        try:
            import gpxpy
            import gpxpy.gpx
        except ImportError:
            logger.warning("gpxpy 未安装，尝试用 XML 解析器 fallback")
            return GPXParser._parse_xml_fallback(file_path)

        waypoints = []
        with open(file_path, "r", encoding="utf-8") as f:
            gpx = gpxpy.parse(f)
        for track in gpx.tracks:
            for segment in track.segments:
                for point in segment.points:
                    speed = None
                    try:
                        speed = point.speed
                        if speed is not None:
                            speed = speed * 3.6
                    except Exception:
                        pass
                    wp = Waypoint(
                        timestamp=point.time.replace(tzinfo=None) if point.time else None,
                        latitude=point.latitude,
                        longitude=point.longitude,
                        elevation=point.elevation,
                        speed=speed,
                    )
                    waypoints.append(wp)
        return waypoints

    @staticmethod
    def _parse_xml_fallback(file_path: str) -> List[Waypoint]:
        import xml.etree.ElementTree as ET
        waypoints = []
        ns = {"gpx": "http://www.topografix.com/GPX/1/1"}
        tree = ET.parse(file_path)
        root = tree.getroot()
        for trkpt in root.iter("{http://www.topografix.com/GPX/1/1}trkpt"):
            lat = float(trkpt.get("lat", 0))
            lon = float(trkpt.get("lon", 0))
            ele_elem = trkpt.find("{http://www.topografix.com/GPX/1/1}ele")
            time_elem = trkpt.find("{http://www.topografix.com/GPX/1/1}time")
            elevation = float(ele_elem.text) if ele_elem is not None and ele_elem.text else None
            ts = None
            if time_elem is not None and time_elem.text:
                ts = parse_datetime(time_elem.text)
            waypoints.append(Waypoint(
                timestamp=ts, latitude=lat, longitude=lon, elevation=elevation
            ))
        return waypoints


class CSVTrackParser:
    """CSV 轨迹文件解析器"""

    @staticmethod
    def parse(file_path: str) -> List[Waypoint]:
        waypoints = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                lat = float(row.get("latitude") or row.get("lat") or 0)
                lon = float(row.get("longitude") or row.get("lon") or row.get("lng") or 0)
                ts = parse_datetime(row.get("timestamp") or row.get("time") or "")
                if lat and lon:
                    waypoints.append(Waypoint(
                        timestamp=ts,
                        latitude=lat,
                        longitude=lon,
                        elevation=float(row.get("elevation") or 0) if row.get("elevation") else None,
                        speed=float(row.get("speed") or 0) if row.get("speed") else None,
                    ))
        return waypoints


def parse_gps_track(file_path: str) -> List[Waypoint]:
    """根据扩展名选择解析器"""
    ext = Path(file_path).suffix.lower()
    if ext == ".gpx":
        return GPXParser.parse(file_path)
    elif ext in (".csv", ".tsv"):
        return CSVTrackParser.parse(file_path)
    elif ext == ".kml":
        logger.warning("KML 解析暂未完整实现，建议转换为 GPX")
        return []
    else:
        raise ValueError(f"不支持的 GPS 文件格式: {ext}")


# ---------------------------------------------------------------------------
# 照片 EXIF 解析
# ---------------------------------------------------------------------------

class PhotoParser:
    """照片 EXIF 解析器"""

    @staticmethod
    def _rational_to_degrees(value) -> float:
        d, m, s = value
        return d + (m / 60.0) + (s / 3600.0)

    @staticmethod
    def parse_directory(dir_path: str) -> List[Photo]:
        if not os.path.isdir(dir_path):
            logger.warning(f"照片目录不存在: {dir_path}")
            return []
        photos = []
        for root, _, files in os.walk(dir_path):
            for fn in sorted(files):
                if fn.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp")):
                    fp = os.path.join(root, fn)
                    photos.append(PhotoParser.parse_file(fp))
        return sorted([p for p in photos if p.timestamp], key=lambda p: p.timestamp)

    @staticmethod
    def parse_file(file_path: str) -> Photo:
        photo = Photo(file_path=file_path)
        try:
            from PIL import Image, ExifTags
            with Image.open(file_path) as img:
                exif = img._getexif() if hasattr(img, "_getexif") else None
                if exif:
                    exif_dict = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                    dt_str = exif_dict.get("DateTimeOriginal") or exif_dict.get("DateTime")
                    if dt_str:
                        try:
                            photo.timestamp = datetime.strptime(str(dt_str), "%Y:%m:%d %H:%M:%S")
                        except Exception:
                            photo.timestamp = parse_datetime(str(dt_str))
                    gps_info = exif_dict.get("GPSInfo")
                    if gps_info and isinstance(gps_info, dict):
                        gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_info.items()}
                        lat_ref = gps.get("GPSLatitudeRef", "N")
                        lon_ref = gps.get("GPSLongitudeRef", "E")
                        if "GPSLatitude" in gps and "GPSLongitude" in gps:
                            lat = PhotoParser._rational_to_degrees(gps["GPSLatitude"])
                            lon = PhotoParser._rational_to_degrees(gps["GPSLongitude"])
                            if lat_ref in ("S", "s"):
                                lat = -lat
                            if lon_ref in ("W", "w"):
                                lon = -lon
                            photo.latitude = lat
                            photo.longitude = lon
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"读取 EXIF 失败 {file_path}: {e}")
        if photo.timestamp is None:
            mtime = os.path.getmtime(file_path)
            photo.timestamp = datetime.fromtimestamp(mtime)
        photo.description = os.path.splitext(os.path.basename(file_path))[0]
        return photo


# ---------------------------------------------------------------------------
# 目的地与备注文件解析
# ---------------------------------------------------------------------------

class DestinationParser:
    """目的地 Markdown 解析器"""

    @staticmethod
    def parse(file_path: str) -> List[Destination]:
        if not os.path.exists(file_path):
            logger.warning(f"目的地文件不存在: {file_path}")
            return []
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        destinations = []
        order = 0
        current = None
        lines = content.splitlines()
        for line in lines:
            line = line.rstrip()
            m = re.match(r'^(#+)\s+(.*)', line)
            if m:
                level = len(m.group(1))
                title = clean_text(m.group(2))
                if level <= 2:
                    if current:
                        destinations.append(current)
                    order += 1
                    current = Destination(name=title, order=order)
                else:
                    if current:
                        current.description += f"\n**{title}**\n"
            elif current:
                current.description += line + "\n"
        if current:
            destinations.append(current)
        for d in destinations:
            d.description = clean_text(d.description)
            m = re.search(r'(-?\d+\.\d+)\s*[,，]\s*(-?\d+\.\d+)', d.description)
            if m:
                d.latitude = float(m.group(1))
                d.longitude = float(m.group(2))
        return destinations


class NoteParser:
    """文字备注解析器（Markdown / CSV）"""

    @staticmethod
    def parse(file_path: str) -> List[Note]:
        if not os.path.exists(file_path):
            logger.warning(f"备注文件不存在: {file_path}")
            return []
        ext = Path(file_path).suffix.lower()
        if ext in (".csv", ".tsv"):
            return NoteParser._parse_csv(file_path)
        else:
            return NoteParser._parse_markdown(file_path)

    @staticmethod
    def _parse_markdown(file_path: str) -> List[Note]:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        notes = []
        pattern = re.compile(
            r'(?:^|\n)\s*[-*]\s*\[(?P<time>[^\]]+)\]\s*(?P<content>.*?)(?=\n\s*[-*]\s*\[|$)',
            re.DOTALL
        )
        pattern2 = re.compile(
            r'(?:^|\n)#{1,6}\s*\[(?P<time>[^\]]+)\]\s*(?P<content>.*?)(?=\n#{1,6}\s*\[|$)',
            re.DOTALL
        )
        for m in list(pattern.finditer(content)) + list(pattern2.finditer(content)):
            time_str = clean_text(m.group("time"))
            text = clean_text(m.group("content"))
            ts = parse_datetime(time_str)
            if text:
                notes.append(Note(
                    timestamp=ts,
                    content=text,
                    tags=extract_tags_from_text(text),
                ))
        if not notes:
            ts_pattern = re.compile(
                r'(?P<time>\d{4}[-/]\d{2}[-/]\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)'
                r'[\s:：-]+(?P<content>.+?)(?=\n\s*\d{4}[-/]\d{2}[-/]\d{2}|$)',
                re.DOTALL
            )
            for m in ts_pattern.finditer(content):
                text = clean_text(m.group("content"))
                if text:
                    notes.append(Note(
                        timestamp=parse_datetime(m.group("time")),
                        content=text,
                        tags=extract_tags_from_text(text),
                    ))
        return sorted([n for n in notes if n.timestamp], key=lambda n: n.timestamp)

    @staticmethod
    def _parse_csv(file_path: str) -> List[Note]:
        notes = []
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = parse_datetime(row.get("timestamp") or row.get("time") or "")
                content = clean_text(row.get("content") or row.get("note") or row.get("text") or "")
                if content:
                    tags = extract_tags_from_text(content)
                    tag_field = row.get("tags") or ""
                    if tag_field:
                        tags.extend([t.strip() for t in re.split(r'[,，;；]', tag_field) if t.strip()])
                    notes.append(Note(
                        timestamp=ts,
                        content=content,
                        tags=tags,
                        location=clean_text(row.get("location") or ""),
                    ))
        return sorted([n for n in notes if n.timestamp], key=lambda n: n.timestamp)


# ---------------------------------------------------------------------------
# 轨迹分段与事件归类
# ---------------------------------------------------------------------------

class TrackSegmenter:
    """将连续轨迹点分割为行驶段与停留段"""

    STOP_MIN_DURATION = timedelta(minutes=3)
    STOP_MAX_DISTANCE = 0.05  # km
    DRIVING_MIN_SPEED = 5.0   # km/h
    TIME_GAP_THRESHOLD = timedelta(hours=2)  # 相邻点超过2小时间隔强制切分

    def segment(self, waypoints: List[Waypoint]) -> List[Dict[str, Any]]:
        """返回分段列表，每段是 driving 或 stop"""
        if not waypoints:
            return []
        segments = []
        current_start = 0
        current_type = None
        prev_wp = waypoints[0]
        i = 1
        while i < len(waypoints):
            wp = waypoints[i]
            forced_split = False
            if prev_wp.timestamp and wp.timestamp:
                gap = wp.timestamp - prev_wp.timestamp
                if gap > self.TIME_GAP_THRESHOLD:
                    forced_split = True
            seg_dist = haversine_distance(
                prev_wp.latitude, prev_wp.longitude, wp.latitude, wp.longitude
            )
            delta_t = (wp.timestamp - prev_wp.timestamp).total_seconds() / 3600 if prev_wp.timestamp and wp.timestamp else 0
            instant_speed = seg_dist / delta_t if delta_t > 0 else 0
            effective_speed = wp.speed if wp.speed is not None else instant_speed
            seg_type = "driving" if effective_speed >= self.DRIVING_MIN_SPEED else "stop"
            if current_type is None:
                current_type = seg_type
            elif forced_split:
                segments.append(self._make_segment(current_type, waypoints[current_start:i]))
                current_start = i
                current_type = seg_type
            elif seg_type != current_type:
                if current_type == "stop":
                    total_dur = (waypoints[i-1].timestamp - waypoints[current_start].timestamp) \
                        if waypoints[i-1].timestamp and waypoints[current_start].timestamp else timedelta(0)
                    total_disp = haversine_distance(
                        waypoints[current_start].latitude, waypoints[current_start].longitude,
                        waypoints[i-1].latitude, waypoints[i-1].longitude
                    )
                    if total_dur < self.STOP_MIN_DURATION:
                        seg_type = current_type
                if seg_type != current_type:
                    segments.append(self._make_segment(current_type, waypoints[current_start:i]))
                    current_start = i
                    current_type = seg_type
            prev_wp = wp
            i += 1
        if current_start < len(waypoints):
            segments.append(self._make_segment(current_type, waypoints[current_start:]))
        return self._merge_short_stops(segments)

    def _make_segment(self, seg_type: str, wps: List[Waypoint]) -> Dict[str, Any]:
        if not wps:
            return {"type": seg_type, "waypoints": [], "duration": 0, "distance": 0}
        duration = (wps[-1].timestamp - wps[0].timestamp).total_seconds() / 60 \
            if wps[0].timestamp and wps[-1].timestamp else 0
        distance = 0.0
        for j in range(1, len(wps)):
            distance += haversine_distance(
                wps[j-1].latitude, wps[j-1].longitude, wps[j].latitude, wps[j].longitude
            )
        return {
            "type": seg_type,
            "waypoints": wps,
            "start_time": wps[0].timestamp,
            "end_time": wps[-1].timestamp,
            "start_lat": wps[0].latitude,
            "start_lon": wps[0].longitude,
            "end_lat": wps[-1].latitude,
            "end_lon": wps[-1].longitude,
            "duration": duration,
            "distance": distance,
            "avg_speed": (distance / (duration / 60)) if duration > 0 else 0,
        }

    def _merge_short_stops(self, segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = []
        i = 0
        while i < len(segments):
            seg = segments[i]
            if seg["type"] == "stop" and seg["duration"] < 3:
                if i + 1 < len(segments) and segments[i+1]["type"] == "driving":
                    if merged and merged[-1]["type"] == "driving":
                        merged[-1] = self._merge_driving_segments(merged[-1], segments[i+1])
                    else:
                        merged.append(segments[i+1])
                    i += 2
                    continue
            merged.append(seg)
            i += 1
        return merged

    def _merge_driving_segments(self, s1: Dict, s2: Dict) -> Dict:
        return {
            "type": "driving",
            "waypoints": s1["waypoints"] + s2["waypoints"],
            "start_time": s1["start_time"],
            "end_time": s2["end_time"],
            "start_lat": s1["start_lat"],
            "start_lon": s1["start_lon"],
            "end_lat": s2["end_lat"],
            "end_lon": s2["end_lon"],
            "duration": s1["duration"] + s2["duration"],
            "distance": s1["distance"] + s2["distance"],
            "avg_speed": ((s1["distance"] + s2["distance"]) / ((s1["duration"] + s2["duration"]) / 60))
                if (s1["duration"] + s2["duration"]) > 0 else 0,
        }


class EventClassifier:
    """根据上下文（时间、关键词、位置）把段/照片/备注归类为 EventType"""

    KEYWORDS = {
        EventType.LUNCH: ["午餐", "吃饭", "午饭", "午饭", "餐厅", "餐馆", "饭馆", "吃饭", "用餐"],
        EventType.DINNER: ["晚餐", "晚饭", "夜宵", "餐厅", "晚饭"],
        EventType.HOTEL_CHECKIN: ["入住", "酒店", "民宿", "住宿", "宾馆", "客栈", "check in", "check-in"],
        EventType.FUEL: ["加油", "加油站", "油费", "中石化", "中石油"],
        EventType.TRAFFIC_JAM: ["堵车", "塞车", "拥堵", "修路", "施工", "封路"],
        EventType.REST: ["休息", "服务区", "休息区", "停车区", "WC", "卫生间", "厕所"],
        EventType.SCENIC_STOP: ["观景台", "景点", "景区", "打卡", "停车拍照", "风景", "垭口", "瀑布", "湖泊"],
        EventType.PHOTO: ["拍照", "照片", "摄影", "拍摄"],
    }

    @classmethod
    def classify_stop(cls, seg: Dict, photos: List[Photo], notes: List[Note],
                      destinations: List[Destination]) -> Tuple[EventType, str]:
        if not seg["start_time"]:
            return EventType.OTHER, "停留"
        h = seg["start_time"].hour
        text_blobs = []
        for n in notes:
            if n.timestamp and seg["start_time"] <= n.timestamp <= (seg["end_time"] or seg["start_time"]):
                text_blobs.append(n.content)
        combined = " ".join(text_blobs)
        type_hits = {}
        for etype, kws in cls.KEYWORDS.items():
            for kw in kws:
                cnt = combined.count(kw)
                if cnt > 0:
                    type_hits[etype] = type_hits.get(etype, 0) + cnt
        time_weights = {
            EventType.LUNCH: 3 if 11 <= h <= 13 else (1 if 10 <= h <= 14 else 0),
            EventType.DINNER: 3 if 18 <= h <= 21 else (1 if 17 <= h <= 22 else 0),
            EventType.HOTEL_CHECKIN: 4 if (20 <= h or h <= 6) else (2 if 16 <= h <= 23 else 0),
            EventType.SCENIC_STOP: 2 if 8 <= h <= 18 else 0,
            EventType.PHOTO: 2 if 7 <= h <= 20 else 0,
            EventType.FUEL: 1 if 7 <= h <= 22 else 0,
            EventType.REST: 1,
        }
        best_type, best_score = EventType.OTHER, 0
        for etype, raw in type_hits.items():
            score = raw * 10 + time_weights.get(etype, 0)
            if score > best_score:
                best_score, best_type = score, etype
        if best_score == 0:
            if len(photos) >= 2:
                best_type = EventType.SCENIC_STOP
            elif 11 <= h <= 13:
                best_type = EventType.LUNCH
            elif 18 <= h <= 21:
                best_type = EventType.DINNER
            elif 20 <= h or h <= 6:
                best_type = EventType.HOTEL_CHECKIN
            elif seg["duration"] > 30:
                best_type = EventType.SCENIC_STOP
            else:
                best_type = EventType.REST
        title = cls._default_title(best_type, h, seg)
        for dest in destinations:
            if dest.latitude is not None:
                d = haversine_distance(seg["start_lat"], seg["start_lon"], dest.latitude, dest.longitude)
                if d < 5.0:
                    title = dest.name
                    break
        return best_type, title

    @classmethod
    def classify_driving(cls, seg: Dict, notes: List[Note]) -> Tuple[EventType, str]:
        h = seg["start_time"].hour if seg["start_time"] else 12
        text_blobs = []
        for n in notes:
            if n.timestamp and seg["start_time"] and seg["end_time"] \
                    and seg["start_time"] <= n.timestamp <= seg["end_time"]:
                text_blobs.append(n.content)
        combined = " ".join(text_blobs)
        for kw in cls.KEYWORDS[EventType.TRAFFIC_JAM]:
            if kw in combined:
                return EventType.TRAFFIC_JAM, "堵车"
        avg_speed = seg.get("avg_speed", 0)
        if avg_speed > 0 and avg_speed < 10 and seg["duration"] > 10:
            return EventType.TRAFFIC_JAM, "堵车"
        tod = classify_time_of_day(seg["start_time"]) if seg["start_time"] else ""
        title = f"{tod}行驶" if tod else "行驶"
        return EventType.DRIVING, title

    @staticmethod
    def _default_title(etype: EventType, h: int, seg: Dict) -> str:
        tod = classify_time_of_day(seg["start_time"]) if seg["start_time"] else ""
        if etype == EventType.LUNCH:
            return "午餐"
        if etype == EventType.DINNER:
            return "晚餐"
        if etype == EventType.HOTEL_CHECKIN:
            return "住宿入住"
        if etype == EventType.FUEL:
            return "加油"
        if etype == EventType.TRAFFIC_JAM:
            return "堵车"
        if etype == EventType.REST:
            return "中途休息"
        if etype == EventType.SCENIC_STOP:
            return f"{tod}观景停留" if tod else "观景停留"
        if etype == EventType.PHOTO:
            return "拍照打卡"
        if etype == EventType.DEPARTURE:
            return "早晨出发"
        return "停留"

    @classmethod
    def classify_from_note(cls, note: Note) -> Tuple[EventType, str]:
        """根据单条备注的关键词和时间推断事件类型"""
        content = note.content or ""
        h = note.timestamp.hour if note.timestamp else 12
        best_type, best_score = EventType.OTHER, 0
        for etype, kws in cls.KEYWORDS.items():
            score = sum(content.count(kw) for kw in kws)
            if score > best_score:
                best_score, best_type = score, etype
        if best_score == 0:
            if "住宿" in content or "酒店" in content or "民宿" in content or "入住" in content:
                best_type = EventType.HOTEL_CHECKIN
            elif "加油" in content or "油" in content and "费" in content:
                best_type = EventType.FUEL
            elif 11 <= h <= 13:
                best_type = EventType.LUNCH
            elif 18 <= h <= 21:
                best_type = EventType.DINNER
            elif 20 <= h or h <= 6:
                best_type = EventType.HOTEL_CHECKIN
            elif "推荐" in content or "太美" in content:
                best_type = EventType.SCENIC_STOP
        title_map = {
            EventType.LUNCH: "午餐",
            EventType.DINNER: "晚餐",
            EventType.HOTEL_CHECKIN: "住宿入住",
            EventType.FUEL: "加油",
            EventType.TRAFFIC_JAM: "堵车",
            EventType.REST: "中途休息",
            EventType.SCENIC_STOP: "观景停留",
            EventType.PHOTO: "拍照打卡",
            EventType.DEPARTURE: "早晨出发",
            EventType.NOTE: "备注",
            EventType.OTHER: "备注",
        }
        title = title_map.get(best_type, content[:12] if content else "备注")
        return best_type, title


# ---------------------------------------------------------------------------
# 组装初版路书
# ---------------------------------------------------------------------------

class RoadbookAssembler:
    """把 GPS+照片+备注+目的地 组装成初版路书"""

    def __init__(self,
                 destinations: List[Destination],
                 waypoints: List[Waypoint],
                 photos: List[Photo],
                 notes: List[Note]):
        self.destinations = destinations
        self.waypoints = sorted([w for w in waypoints if w.timestamp], key=lambda w: w.timestamp)
        self.photos = photos
        self.notes = notes
        self.segmenter = TrackSegmenter()
        self.classifier = EventClassifier()

    def build(self) -> Roadbook:
        if not self.waypoints:
            raise ValueError("GPS 轨迹为空，无法构建路书")
        segments = self.segmenter.segment(self.waypoints)
        mileage_timeline = build_mileage_timeline(segments)
        events = []
        cumulative_km = 0.0
        covered_note_contents = set()
        for seg in segments:
            seg_photos = self._photos_in_range(seg.get("start_time"), seg.get("end_time"))
            seg_notes = self._notes_in_range(seg.get("start_time"), seg.get("end_time"))
            for n in seg_notes:
                covered_note_contents.add(id(n))
            if seg["type"] == "driving":
                etype, title = self.classifier.classify_driving(seg, seg_notes)
                dist = seg["distance"]
                cumulative_km += dist
                evt = self._make_event(
                    timestamp=seg["start_time"], etype=etype, title=title,
                    lat=seg["start_lat"], lon=seg["start_lon"],
                    duration=int(seg["duration"]), distance=dist,
                    cumulative=cumulative_km, avg_speed=seg["avg_speed"],
                    photos=seg_photos, notes=seg_notes, end_lat=seg["end_lat"], end_lon=seg["end_lon"],
                    mileage_timeline=mileage_timeline
                )
            else:
                etype, title = self.classifier.classify_stop(seg, seg_photos, seg_notes, self.destinations)
                evt = self._make_event(
                    timestamp=seg["start_time"], etype=etype, title=title,
                    lat=seg["start_lat"], lon=seg["start_lon"],
                    duration=int(seg["duration"]), distance=0,
                    cumulative=cumulative_km, photos=seg_photos, notes=seg_notes,
                    mileage_timeline=mileage_timeline
                )
            events.append(evt)
        orphan_photos = [p for p in self.photos if not any(p in e.photos for e in events)]
        for p in orphan_photos:
            km_orphan = lookup_cumulative_mileage(mileage_timeline, p.timestamp)
            events.append(RoadEvent(
                event_id=generate_event_id("photo"),
                timestamp=p.timestamp or datetime.now(),
                event_type=EventType.PHOTO,
                title=f"拍照打卡 - {p.description}",
                description=p.description,
                latitude=p.latitude, longitude=p.longitude,
                photos=[p],
                cumulative_km=round(km_orphan, 2),
                highlights=[p.description] if p.description else [],
            ))
        orphan_notes = [n for n in self.notes if id(n) not in covered_note_contents]
        for n in orphan_notes:
            etype, title = self.classifier.classify_from_note(n)
            costs = extract_costs(n.content, n.tags)
            cb = cost_breakdown_to_fields(costs)
            pitfall_list = self._extract_pitfalls(n.content)
            pit_cats = list(dict.fromkeys(categorize_pitfall(p) for p in pitfall_list))
            km_orphan = lookup_cumulative_mileage(mileage_timeline, n.timestamp)
            rating = None
            for m in re.finditer(r'(\d+(?:\.\d+)?)\s*分', n.content):
                try:
                    s = int(float(m.group(1)))
                    if 1 <= s <= 5:
                        rating = s
                except ValueError:
                    pass
            events.append(RoadEvent(
                event_id=generate_event_id(etype.value),
                timestamp=n.timestamp or datetime.now(),
                event_type=etype,
                title=title,
                description=n.content,
                tags=n.tags,
                cumulative_km=round(km_orphan, 2),
                fuel_cost=round(costs.get("fuel_cost", 0.0), 2),
                toll_cost=round(costs.get("toll_cost", 0.0), 2),
                other_cost=round(cb["other_cost"], 2),
                cost_breakdown=cb["_breakdown"],
                pitfalls=pitfall_list,
                pitfall_categories=pit_cats,
                highlights=self._extract_highlights(n.content),
                rating=rating,
            ))
        events.sort(key=lambda e: e.timestamp or datetime.min)
        self._mark_departure(events)
        days = self._group_by_day(events)
        return self._finalize_roadbook(days)

    @staticmethod
    def _extract_pitfalls(content: str) -> List[str]:
        pitfalls = []
        for kw in ["坑", "避坑", "注意", "警告", "别", "不要", "小心"]:
            if kw in content:
                pitfalls.append(content)
                break
        return pitfalls

    @staticmethod
    def _extract_highlights(content: str) -> List[str]:
        highlights = []
        for kw in ["推荐", "值得", "必去", "太美", "惊喜", "震撼", "强烈推荐"]:
            if kw in content:
                highlights.append(content)
                break
        return highlights

    def _make_event(self, timestamp, etype, title, lat, lon, duration, distance,
                    cumulative, avg_speed=None, photos=None, notes=None,
                    end_lat=None, end_lon=None, mileage_timeline=None):
        description_parts = []
        tags = []
        pitfalls = []
        pitfall_categories = []
        highlights = []
        rating = None
        road_condition_score = None
        driving_difficulty = None
        total_fuel = 0.0
        total_toll = 0.0
        total_other = 0.0
        cost_breakdown = {"accommodation": 0.0, "food": 0.0, "ticket": 0.0,
                         "parking": 0.0, "other": 0.0, "per_person": None}
        for n in (notes or []):
            description_parts.append(n.content)
            tags.extend(n.tags)
            content = n.content
            for kw in ["坑", "避坑", "注意", "警告", "别", "不要", "小心"]:
                if kw in content:
                    pitfalls.append(content)
                    cat = categorize_pitfall(content)
                    if cat not in pitfall_categories:
                        pitfall_categories.append(cat)
                    break
            for kw in ["推荐", "值得", "必去", "太美", "惊喜", "震撼"]:
                if kw in content:
                    highlights.append(content)
                    break
            costs = extract_costs(content, n.tags)
            total_fuel += costs.get("fuel_cost", 0.0)
            total_toll += costs.get("toll_cost", 0.0)
            mapped = cost_breakdown_to_fields(costs)
            total_other += mapped["other_cost"]
            for k in ["accommodation", "food", "ticket", "parking", "other"]:
                cost_breakdown[k] += mapped["_breakdown"].get(k, 0.0)
            if cost_breakdown["per_person"] is None:
                cost_breakdown["per_person"] = costs.get("per_person")
            for m in re.finditer(r'(\d+(?:\.\d+)?)\s*分', content):
                try:
                    score = int(float(m.group(1)))
                    if 1 <= score <= 5:
                        rating = score
                except ValueError:
                    pass
        description = "\n\n".join(description_parts)
        if etype in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM):
            if avg_speed is not None:
                if avg_speed >= 60:
                    road_condition_score = 5
                    driving_difficulty = "简单"
                elif avg_speed >= 40:
                    road_condition_score = 4
                    driving_difficulty = "简单"
                elif avg_speed >= 25:
                    road_condition_score = 3
                    driving_difficulty = "中等"
                elif avg_speed >= 15:
                    road_condition_score = 2
                    driving_difficulty = "困难"
                else:
                    road_condition_score = 1
                    driving_difficulty = "地狱"
            if etype == EventType.TRAFFIC_JAM:
                road_condition_score = max(1, (road_condition_score or 3) - 2)
                if "修路" in description or "烂路" in description:
                    driving_difficulty = "困难"
                    road_condition_score = 1
        km_at_start = cumulative
        if mileage_timeline and timestamp:
            km_at_start = lookup_cumulative_mileage(mileage_timeline, timestamp)
        return RoadEvent(
            event_id=generate_event_id(etype.value),
            timestamp=timestamp or datetime.now(),
            event_type=etype,
            title=title,
            description=description,
            latitude=lat, longitude=lon,
            duration_minutes=duration,
            distance_km=round(distance, 2),
            cumulative_km=round(km_at_start, 2),
            avg_speed=round(avg_speed, 1) if avg_speed else None,
            fuel_cost=round(total_fuel, 2),
            toll_cost=round(total_toll, 2),
            other_cost=round(total_other, 2),
            cost_breakdown={k: (round(v, 2) if isinstance(v, float) else v) for k, v in cost_breakdown.items()},
            photos=photos or [],
            tags=list(dict.fromkeys(tags)),
            pitfalls=pitfalls,
            pitfall_categories=pitfall_categories,
            highlights=highlights,
            rating=rating,
            road_condition_score=road_condition_score,
            driving_difficulty=driving_difficulty,
        )

    def _photos_in_range(self, start, end) -> List[Photo]:
        if not start or not end:
            return []
        return [p for p in self.photos if p.timestamp and start <= p.timestamp <= end]

    def _notes_in_range(self, start, end) -> List[Note]:
        if not start or not end:
            return []
        return [n for n in self.notes if n.timestamp and start <= n.timestamp <= end]

    def _mark_departure(self, events: List[RoadEvent]) -> None:
        """把每天第一段非夜间驾驶或停留标记为出发"""
        seen_days = set()
        for e in events:
            if not e.timestamp:
                continue
            day_key = e.timestamp.date()
            if day_key in seen_days:
                continue
            h = e.timestamp.hour
            if 5 <= h <= 10:
                if e.event_type in (EventType.DRIVING, EventType.OTHER):
                    e.event_type = EventType.DEPARTURE
                    e.title = "早晨出发"
                    seen_days.add(day_key)
            elif e.event_type == EventType.DRIVING or e.event_type == EventType.SCENIC_STOP:
                seen_days.add(day_key)

    def _group_by_day(self, events: List[RoadEvent]) -> List[DayPlan]:
        buckets: Dict[Any, List[RoadEvent]] = {}
        for e in events:
            if e.timestamp:
                key = e.timestamp.date()
            else:
                key = "unknown"
            buckets.setdefault(key, []).append(e)
        days = []
        for idx, (date_key, evts) in enumerate(sorted(buckets.items()), start=1):
            date_str = str(date_key) if isinstance(date_key, type(datetime.now().date())) else "未知"
            total_km = 0.0
            total_cost = 0.0
            total_dur = 0.0
            photo_count = 0
            cost_bd = {"fuel": 0.0, "toll": 0.0, "accommodation": 0.0,
                       "food": 0.0, "ticket": 0.0, "parking": 0.0, "other": 0.0}
            diff_counter = {"简单": 0, "中等": 0, "困难": 0, "地狱": 0}
            for e in evts:
                if e.event_type in (EventType.DRIVING, EventType.TRAFFIC_JAM, EventType.DEPARTURE):
                    total_km += e.distance_km
                total_cost += e.total_cost
                total_dur += e.duration_minutes
                photo_count += len(e.photos)
                cost_bd["fuel"] += e.fuel_cost
                cost_bd["toll"] += e.toll_cost
                bd = e.cost_breakdown or {}
                cost_bd["accommodation"] += bd.get("accommodation", 0.0)
                cost_bd["food"] += bd.get("food", 0.0)
                cost_bd["ticket"] += bd.get("ticket", 0.0)
                cost_bd["parking"] += bd.get("parking", 0.0)
                cost_bd["other"] += bd.get("other", 0.0)
                if e.driving_difficulty in diff_counter:
                    diff_counter[e.driving_difficulty] += 1
            start = evts[0].title if evts else ""
            end = evts[-1].title if evts else ""
            difficulty_avg = None
            if sum(diff_counter.values()) > 0:
                for k in ["地狱", "困难", "中等", "简单"]:
                    if diff_counter[k] > 0:
                        difficulty_avg = k
                        break
            summary = f"{date_str}: 行驶 {total_km:.1f} 公里，耗时 {total_dur/60:.1f} 小时，费用 {total_cost:.0f} 元"
            days.append(DayPlan(
                day_index=idx,
                date=date_str,
                title=f"第 {idx} 天 · {date_str}",
                summary=summary,
                events=evts,
                start_location=start,
                end_location=end,
                total_distance_km=round(total_km, 1),
                total_duration_hours=round(total_dur / 60, 1),
                total_cost=round(total_cost, 2),
                cost_breakdown={k: round(v, 2) for k, v in cost_bd.items()},
                photo_count=photo_count,
                driving_difficulty_avg=difficulty_avg,
            ))
        return days

    def _finalize_roadbook(self, days: List[DayPlan]) -> Roadbook:
        total_km = sum(d.total_distance_km for d in days)
        total_cost = sum(d.total_cost for d in days)
        start_date = days[0].date if days else ""
        end_date = days[-1].date if days else ""
        dest_names = " → ".join(d.name for d in self.destinations) if self.destinations else ""
        title = dest_names or f"自驾路书 {start_date} 至 {end_date}"
        cost_bd_total = {"fuel": 0.0, "toll": 0.0, "accommodation": 0.0,
                         "food": 0.0, "ticket": 0.0, "parking": 0.0, "other": 0.0}
        for d in days:
            for k in cost_bd_total:
                cost_bd_total[k] += d.cost_breakdown.get(k, 0.0)
        photo_spots = []
        all_events = [e for d in days for e in d.events]
        GENERIC_TITLES = {"拍照打卡", "拍照", "观景", "观景停留", "下午观景停留",
                          "上午观景停留", "傍晚观景停留", "路边停留", "临时停车"}
        named_destinations = [d for d in self.destinations if d.latitude is not None and d.longitude is not None]

        def _resolve_spot_name(event: RoadEvent) -> str:
            if event.title and event.title not in GENERIC_TITLES:
                return event.title
            if event.latitude is not None and event.longitude is not None and named_destinations:
                best = None
                best_dist = float("inf")
                for d in named_destinations:
                    dist = haversine_distance(event.latitude, event.longitude, d.latitude, d.longitude)
                    if dist < best_dist:
                        best_dist = dist
                        best = d
                if best is not None and best_dist < 50:
                    return best.name
            if event.title:
                return event.title
            return "观景停留"

        for e in all_events:
            if e.event_type in (EventType.SCENIC_STOP, EventType.PHOTO) or len(e.photos) >= 1:
                grade = "S" if len(e.photos) >= 4 or "必去" in (e.description or "") \
                              or "强烈推荐" in (e.description or "") else (
                         "A" if len(e.photos) >= 2 or "推荐" in (e.description or "") else "B")
                cb = e.cost_breakdown or {}
                photo_spots.append({
                    "name": _resolve_spot_name(e),
                    "level": grade,
                    "day": next((d.day_index for d in days if e in d.events), 0),
                    "time": e.timestamp.strftime("%H:%M") if e.timestamp else "",
                    "latitude": e.latitude,
                    "longitude": e.longitude,
                    "photo_count": len(e.photos),
                    "grade": grade,
                    "tickets": cb.get("ticket") if isinstance(cb.get("ticket"), (int, float)) else None,
                    "parking_fee": cb.get("parking") if isinstance(cb.get("parking"), (int, float)) else None,
                    "stay_minutes": int(e.duration_minutes) if e.duration_minutes else None,
                    "highlights": e.highlights[:3],
                    "tips": e.pitfalls[:2],
                })
        photo_spots.sort(key=lambda x: {"S": 0, "A": 1, "B": 2}.get(x["grade"], 3))
        pitfalls_by_category: Dict[str, List[str]] = {
            "费用坑": [], "路况坑": [], "住宿坑": [], "餐饮坑": [], "拍照坑": [], "其他坑": []
        }
        for e in all_events:
            for p in e.pitfalls:
                cat = categorize_pitfall(p)
                pitfalls_by_category.setdefault(cat, []).append(p)
        pitfalls_by_category = {k: list(dict.fromkeys(v)) for k, v in pitfalls_by_category.items() if v}
        road_scores: Dict[str, Any] = {
            "overall_avg": 0.0,
            "segment_count": 0,
            "difficulty_distribution": {"简单": 0, "中等": 0, "困难": 0, "地狱": 0},
            "by_day": {},
            "traffic_jam_count": 0,
            "traffic_jam_minutes": 0,
        }
        total_score = 0.0
        scored_segments = 0
        for d in days:
            day_scores = []
            for e in d.events:
                if e.event_type in (EventType.DRIVING, EventType.DEPARTURE, EventType.TRAFFIC_JAM):
                    if e.road_condition_score is not None:
                        total_score += e.road_condition_score
                        scored_segments += 1
                        day_scores.append(e.road_condition_score)
                    if e.driving_difficulty in road_scores["difficulty_distribution"]:
                        road_scores["difficulty_distribution"][e.driving_difficulty] += 1
                    if e.event_type == EventType.TRAFFIC_JAM:
                        road_scores["traffic_jam_count"] += 1
                        road_scores["traffic_jam_minutes"] += e.duration_minutes
            if day_scores:
                road_scores["by_day"][d.day_index] = round(sum(day_scores) / len(day_scores), 2)
        road_scores["overall_avg"] = round(total_score / scored_segments, 2) if scored_segments > 0 else 0
        road_scores["segment_count"] = scored_segments
        return Roadbook(
            title=title,
            created_at=datetime.now(),
            start_date=start_date,
            end_date=end_date,
            total_days=len(days),
            total_distance_km=round(total_km, 1),
            total_cost=round(total_cost, 2),
            cost_breakdown={k: round(v, 2) for k, v in cost_bd_total.items()},
            destinations=self.destinations,
            days=days,
            photo_spots=photo_spots,
            pitfalls_by_category=pitfalls_by_category,
            road_scores=road_scores,
            meta={"source": "roadtrip-planner v0.2.0",
                  "total_waypoints": len(self.waypoints),
                  "total_photos": len(self.photos),
                  "total_notes": len(self.notes)},
        )


def import_materials(destinations_file: str = "", gps_file: str = "",
                     photos_dir: str = "", notes_file: str = "") -> Roadbook:
    """统一入口：解析所有素材并组装初版路书"""
    destinations = DestinationParser.parse(destinations_file) if destinations_file else []
    waypoints = parse_gps_track(gps_file) if gps_file else []
    if not waypoints:
        logger.warning("未解析到 GPS 轨迹点，请检查文件格式")
    photos = PhotoParser.parse_directory(photos_dir) if photos_dir else []
    notes = NoteParser.parse(notes_file) if notes_file else []
    logger.info(f"解析结果: {len(destinations)} 个目的地, {len(waypoints)} 轨迹点, "
                f"{len(photos)} 张照片, {len(notes)} 条备注")
    assembler = RoadbookAssembler(destinations, waypoints, photos, notes)
    return assembler.build()


# ---------------------------------------------------------------------------
# 素材预检模块
# ---------------------------------------------------------------------------

@dataclass
class PrecheckReport:
    """素材预检报告"""
    destinations_count: int = 0
    destinations_details: List[Dict[str, Any]] = field(default_factory=list)
    gps_points_count: int = 0
    gps_date_range: Optional[Tuple[str, str]] = None
    gps_estimated_km: float = 0.0
    photos_total: int = 0
    photos_with_timestamp: int = 0
    photos_with_gps: int = 0
    photos_missing_timestamp: List[str] = field(default_factory=list)
    notes_total: int = 0
    notes_with_timestamp: int = 0
    notes_without_timestamp: List[str] = field(default_factory=list)
    notes_unmatched_to_gps: List[Dict[str, Any]] = field(default_factory=list)
    cost_matches_preview: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "destinations_count": self.destinations_count,
            "destinations_details": self.destinations_details,
            "gps_points_count": self.gps_points_count,
            "gps_date_range": list(self.gps_date_range) if self.gps_date_range else None,
            "gps_estimated_km": self.gps_estimated_km,
            "photos_total": self.photos_total,
            "photos_with_timestamp": self.photos_with_timestamp,
            "photos_with_gps": self.photos_with_gps,
            "photos_missing_timestamp": self.photos_missing_timestamp,
            "notes_total": self.notes_total,
            "notes_with_timestamp": self.notes_with_timestamp,
            "notes_without_timestamp": self.notes_without_timestamp,
            "notes_unmatched_to_gps": self.notes_unmatched_to_gps,
            "cost_matches_preview": self.cost_matches_preview,
            "warnings": self.warnings,
            "summary": self.summary,
        }

    def to_text(self) -> str:
        lines = []
        lines.append("=" * 60)
        lines.append("  🚗 路书素材预检报告")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"📋 概览: {self.summary}")
        lines.append("")
        lines.append(f"📍 目的地文件: {self.destinations_count} 个")
        for d in self.destinations_details:
            coord = f" ({d['latitude']}, {d['longitude']})" if d.get("latitude") else " (无坐标)"
            lines.append(f"   - 第{d['order']}位: {d['name']}{coord}")
        lines.append("")
        lines.append(f"🛰️ GPS 轨迹: {self.gps_points_count} 个点")
        if self.gps_date_range:
            lines.append(f"   时间跨度: {self.gps_date_range[0]} 至 {self.gps_date_range[1]}")
        lines.append(f"   估算里程: {self.gps_estimated_km:.1f} km")
        lines.append("")
        lines.append(f"📷 照片素材: {self.photos_total} 张")
        lines.append(f"   含时间戳: {self.photos_with_timestamp} / {self.photos_total}")
        lines.append(f"   含GPS定位: {self.photos_with_gps} / {self.photos_total}")
        if self.photos_missing_timestamp:
            lines.append(f"   ⚠️  缺少时间戳 ({len(self.photos_missing_timestamp)}张):")
            for p in self.photos_missing_timestamp[:10]:
                lines.append(f"      - {p}")
        lines.append("")
        lines.append(f"📝 文字备注: {self.notes_total} 条")
        lines.append(f"   含时间戳: {self.notes_with_timestamp} / {self.notes_total}")
        if self.notes_unmatched_to_gps:
            lines.append(f"   ⚠️  无法匹配到 GPS 轨迹 ({len(self.notes_unmatched_to_gps)}条):")
            for n in self.notes_unmatched_to_gps[:10]:
                lines.append(f"      - [{n.get('time','?')}] {n.get('content','')[:30]}...")
        lines.append("")
        if self.cost_matches_preview:
            lines.append(f"💰 识别到的金额 (预览 {len(self.cost_matches_preview)} 条):")
            for c in self.cost_matches_preview:
                lines.append(f"   - [{c.get('category','?')}] {c.get('amount')}元: {c.get('evidence','')[:40]}")
            lines.append("")
        if self.warnings:
            lines.append(f"⚠️  需要注意 ({len(self.warnings)} 条):")
            for w in self.warnings:
                lines.append(f"   - {w}")
        lines.append("")
        lines.append("=" * 60)
        return "\n".join(lines)


def build_precheck_report(destinations_file: str = "", gps_file: str = "",
                          photos_dir: str = "", notes_file: str = "",
                          output_dir: Optional[str] = None) -> PrecheckReport:
    """构建素材预检报告，可选输出JSON+TXT"""
    report = PrecheckReport()
    destinations = DestinationParser.parse(destinations_file) if destinations_file else []
    waypoints = parse_gps_track(gps_file) if gps_file else []
    photos_raw = []
    photos_with_ts = 0
    photos_with_gps = 0
    photos_missing_ts: List[str] = []
    if photos_dir and os.path.isdir(photos_dir):
        for root, _, files in os.walk(photos_dir):
            for fn in sorted(files):
                if fn.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp")):
                    fp = os.path.join(root, fn)
                    photos_raw.append(fp)
        for fp in photos_raw:
            try:
                from PIL import Image, ExifTags
                with Image.open(fp) as img:
                    exif = img._getexif() if hasattr(img, "_getexif") else None
                    has_ts = False
                    has_gps = False
                    if exif:
                        exif_dict = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
                        dt_str = exif_dict.get("DateTimeOriginal") or exif_dict.get("DateTime")
                        if dt_str:
                            has_ts = True
                            photos_with_ts += 1
                        gps_info = exif_dict.get("GPSInfo")
                        if gps_info and isinstance(gps_info, dict):
                            gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_info.items()}
                            if "GPSLatitude" in gps and "GPSLongitude" in gps:
                                has_gps = True
                                photos_with_gps += 1
                    if not has_ts:
                        photos_missing_ts.append(fp)
            except Exception:
                photos_missing_ts.append(fp)
    report.photos_total = len(photos_raw)
    report.photos_with_timestamp = photos_with_ts
    report.photos_with_gps = photos_with_gps
    report.photos_missing_timestamp = photos_missing_ts
    notes = NoteParser.parse(notes_file) if notes_file else []
    report.notes_total = len(notes)
    report.notes_with_timestamp = sum(1 for n in notes if n.timestamp)
    report.notes_without_timestamp = [
        n.content[:50] for n in notes if not n.timestamp
    ]
    report.destinations_count = len(destinations)
    report.destinations_details = [
        {"order": d.order, "name": d.name, "latitude": d.latitude, "longitude": d.longitude,
         "description_length": len(d.description)} for d in destinations
    ]
    report.gps_points_count = len(waypoints)
    waypoints_sorted = sorted([w for w in waypoints if w.timestamp], key=lambda w: w.timestamp)
    if waypoints_sorted:
        report.gps_date_range = (
            waypoints_sorted[0].timestamp.strftime("%Y-%m-%d %H:%M"),
            waypoints_sorted[-1].timestamp.strftime("%Y-%m-%d %H:%M"),
        )
        total_km = 0.0
        for j in range(1, len(waypoints_sorted)):
            total_km += haversine_distance(
                waypoints_sorted[j-1].latitude, waypoints_sorted[j-1].longitude,
                waypoints_sorted[j].latitude, waypoints_sorted[j].longitude
            )
        report.gps_estimated_km = round(total_km, 1)
    if waypoints_sorted and notes:
        t_start = waypoints_sorted[0].timestamp
        t_end = waypoints_sorted[-1].timestamp
        unmatched = []
        for n in notes:
            if n.timestamp and not (t_start <= n.timestamp <= t_end):
                unmatched.append({
                    "time": n.timestamp.strftime("%Y-%m-%d %H:%M") if n.timestamp else "",
                    "content": n.content[:100],
                })
        report.notes_unmatched_to_gps = unmatched
    cost_preview = []
    for n in notes:
        costs = extract_costs(n.content, n.tags)
        for rec in costs.get("matches", []):
            cost_preview.append(rec)
    report.cost_matches_preview = cost_preview[:20]
    warnings = []
    if report.destinations_count == 0:
        warnings.append("未找到目的地，请检查 destinations 文件路径或格式（应为 ## 开头的 Markdown）")
    if report.gps_points_count == 0:
        warnings.append("GPS 轨迹为空，将无法生成路书的里程与驾驶段")
    if report.photos_total == 0:
        warnings.append("未找到照片，建议补充 JPG/PNG 素材以生成拍照点清单")
    if report.photos_missing_timestamp:
        warnings.append(f"{len(photos_missing_ts)} 张照片缺少 EXIF 时间戳，将无法精确匹配到路线")
    if report.notes_total == 0:
        warnings.append("未找到文字备注，费用识别与事件描述将为空")
    if report.notes_unmatched_to_gps:
        warnings.append(f"{len(report.notes_unmatched_to_gps)} 条备注不在 GPS 时间范围内，可能无法生成对应事件")
    report.warnings = warnings
    report.summary = (
        f"{report.destinations_count}个目的地 / {report.gps_points_count}轨迹点 / "
        f"{report.photos_total}张照片 / {report.notes_total}条备注 · "
        f"预估里程{report.gps_estimated_km:.0f}km · 共识别{len(cost_preview)}处金额"
    )
    if output_dir:
        ensure_dir(output_dir)
        save_json(report.to_dict(), os.path.join(output_dir, "precheck_report.json"))
        with open(os.path.join(output_dir, "precheck_report.txt"), "w", encoding="utf-8") as f:
            f.write(report.to_text())
    return report
