"""素材导入模块 - GPS解析、照片EXIF、文件读取、事件归类"""
import os
import re
import csv
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple, Any
from pathlib import Path

from .models import (
    Waypoint, Photo, Destination, Note, RoadEvent, DayPlan, Roadbook, EventType
)
from .utils import (
    haversine_distance, parse_datetime, generate_event_id, classify_time_of_day,
    extract_tags_from_text, clean_text
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
                    photos=seg_photos, notes=seg_notes, end_lat=seg["end_lat"], end_lon=seg["end_lon"]
                )
            else:
                etype, title = self.classifier.classify_stop(seg, seg_photos, seg_notes, self.destinations)
                evt = self._make_event(
                    timestamp=seg["start_time"], etype=etype, title=title,
                    lat=seg["start_lat"], lon=seg["start_lon"],
                    duration=int(seg["duration"]), distance=0,
                    cumulative=cumulative_km, photos=seg_photos, notes=seg_notes
                )
            events.append(evt)
        orphan_photos = [p for p in self.photos if not any(p in e.photos for e in events)]
        for p in orphan_photos:
            events.append(RoadEvent(
                event_id=generate_event_id("photo"),
                timestamp=p.timestamp or datetime.now(),
                event_type=EventType.PHOTO,
                title=f"拍照打卡 - {p.description}",
                description=p.description,
                latitude=p.latitude, longitude=p.longitude,
                photos=[p],
                cumulative_km=cumulative_km,
            ))
        orphan_notes = [n for n in self.notes if id(n) not in covered_note_contents]
        for n in orphan_notes:
            etype, title = self.classifier.classify_from_note(n)
            events.append(RoadEvent(
                event_id=generate_event_id(etype.value),
                timestamp=n.timestamp or datetime.now(),
                event_type=etype,
                title=title,
                description=n.content,
                tags=n.tags,
                cumulative_km=cumulative_km,
                pitfalls=self._extract_pitfalls(n.content),
                highlights=self._extract_highlights(n.content),
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
                    end_lat=None, end_lon=None):
        description_parts = []
        tags = []
        pitfalls = []
        highlights = []
        rating = None
        for n in (notes or []):
            description_parts.append(n.content)
            tags.extend(n.tags)
            content = n.content
            for kw in ["坑", "避坑", "注意", "警告", "别", "不要", "小心"]:
                if kw in content:
                    pitfalls.append(content)
                    break
            for kw in ["推荐", "值得", "必去", "太美", "惊喜", "震撼"]:
                if kw in content:
                    highlights.append(content)
                    break
        description = "\n\n".join(description_parts)
        if etype == EventType.DRIVING and end_lat is not None:
            pass
        return RoadEvent(
            event_id=generate_event_id(etype.value),
            timestamp=timestamp or datetime.now(),
            event_type=etype,
            title=title,
            description=description,
            latitude=lat, longitude=lon,
            duration_minutes=duration,
            distance_km=round(distance, 2),
            cumulative_km=round(cumulative, 2),
            avg_speed=round(avg_speed, 1) if avg_speed else None,
            photos=photos or [],
            tags=list(dict.fromkeys(tags)),
            pitfalls=pitfalls,
            highlights=highlights,
            rating=rating,
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
            for e in evts:
                if e.event_type == EventType.DRIVING or e.event_type == EventType.TRAFFIC_JAM or e.event_type == EventType.DEPARTURE:
                    total_km += e.distance_km
                total_cost += e.total_cost
                total_dur += e.duration_minutes
            start = evts[0].title if evts else ""
            end = evts[-1].title if evts else ""
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
            ))
        return days

    def _finalize_roadbook(self, days: List[DayPlan]) -> Roadbook:
        total_km = sum(d.total_distance_km for d in days)
        total_cost = sum(d.total_cost for d in days)
        start_date = days[0].date if days else ""
        end_date = days[-1].date if days else ""
        dest_names = " → ".join(d.name for d in self.destinations) if self.destinations else ""
        title = dest_names or f"自驾路书 {start_date} 至 {end_date}"
        return Roadbook(
            title=title,
            created_at=datetime.now(),
            start_date=start_date,
            end_date=end_date,
            total_days=len(days),
            total_distance_km=round(total_km, 1),
            total_cost=round(total_cost, 2),
            destinations=self.destinations,
            days=days,
            meta={"source": "roadtrip-planner v0.1.0"},
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
