"""通用工具函数"""
import math
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两经纬度点之间的距离（公里）"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def format_duration(minutes: int) -> str:
    """格式化分钟为 HH 小时 MM 分钟"""
    if minutes < 60:
        return f"{minutes} 分钟"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours} 小时"
    return f"{hours} 小时 {mins} 分钟"


def format_time(dt: datetime) -> str:
    """格式化时间为 HH:MM"""
    return dt.strftime("%H:%M")


def format_date(dt: datetime) -> str:
    """格式化日期为 YYYY-MM-DD"""
    return dt.strftime("%Y-%m-%d")


def format_datetime(dt: datetime) -> str:
    """格式化日期时间为 YYYY-MM-DD HH:MM"""
    return dt.strftime("%Y-%m-%d %H:%M")


def parse_datetime(s: str) -> Optional[datetime]:
    """灵活解析日期时间字符串"""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y:%m:%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    for fmt_with_tz in ("%Y-%m-%dT%H:%M:%S%z",):
        try:
            dt = datetime.strptime(s, fmt_with_tz)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    m = re.match(
        r'(\d{4})[-/:](\d{1,2})[-/:](\d{1,2})[ T](\d{1,2})[-/:](\d{1,2})(?:[-/:](\d{1,2}))?',
        s
    )
    if m:
        try:
            y, mo, d, h, mi = (int(x) for x in m.groups()[:5])
            se = int(m.group(6)) if m.group(6) else 0
            return datetime(y, mo, d, h, mi, se)
        except Exception:
            return None
    return None


def generate_event_id(prefix: str = "evt") -> str:
    """生成事件ID"""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def classify_time_of_day(dt: datetime) -> str:
    """判断时间段：早晨/上午/中午/下午/傍晚/夜间"""
    h = dt.hour
    if 5 <= h < 8:
        return "早晨"
    elif 8 <= h < 11:
        return "上午"
    elif 11 <= h < 13:
        return "中午"
    elif 13 <= h < 17:
        return "下午"
    elif 17 <= h < 20:
        return "傍晚"
    else:
        return "夜间"


def extract_tags_from_text(text: str) -> List[str]:
    """从文本中提取 #标签 """
    if not text:
        return []
    return re.findall(r'#(\w+)', text)


def clean_text(text: str) -> str:
    """清理文本空白"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    return text


def ensure_dir(path: str) -> None:
    """确保目录存在"""
    import os
    os.makedirs(path, exist_ok=True)


def save_json(data: dict, path: str) -> None:
    """保存 JSON 文件"""
    import json
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(path: str) -> dict:
    """加载 JSON 文件"""
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
