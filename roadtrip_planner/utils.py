"""通用工具函数"""
import math
import os
import json
import re
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any


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


# ---------------------------------------------------------------------------
# 费用金额智能提取
# ---------------------------------------------------------------------------

COST_CATEGORY_RULES = {
    "fuel_cost": {
        "keywords": ["加油", "油费", "中石化", "中石油", "92号", "95号", "98号"],
        "patterns": [
            r'(?:加油|油费)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元',
            r'(\d+(?:\.\d+)?)\s*元\s*(?:加油|油费)',
            r'油费(\d+(?:\.\d+)?)',
        ]
    },
    "toll_cost": {
        "keywords": ["过路费", "高速费", "过路费", "ETC", "etc", "过卡"],
        "patterns": [
            r'(?:过路费|高速费|ETC)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元',
            r'(\d+(?:\.\d+)?)\s*元\s*(?:过路费|高速费|ETC)',
        ]
    },
    "accommodation_cost": {
        "keywords": ["住宿", "酒店", "民宿", "客栈", "入住", "房费"],
        "patterns": [
            r'(\d+(?:\.\d+)?)\s*元\s*(?:\/|每|一)?\s*(?:晚|间|夜|房)',
            r'(\d+(?:\.\d+)?)\s*(?:\/|每|一)\s*(?:晚|间|夜|房)',
            r'(?:住宿|酒店|民宿|客栈|房费)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元',
        ]
    },
    "ticket_cost": {
        "keywords": ["门票", "观光车", "景区票", "入园", "套票"],
        "patterns": [
            r'(?:门票|观光车|套票|入园)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元',
            r'(\d+(?:\.\d+)?)\s*元\s*(?:门票|观光车|套票)',
            r'(?:门票|观光车)\+?\s*(?:门票|观光车)?\s*(\d+(?:\.\d+)?)',
        ]
    },
    "parking_cost": {
        "keywords": ["停车费", "停车"],
        "patterns": [
            r'停车费\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元',
            r'(\d+(?:\.\d+)?)\s*元\s*停车费',
        ]
    },
    "food_cost": {
        "keywords": ["午餐", "晚餐", "早餐", "吃饭", "餐厅", "餐馆", "火锅", "汤锅", "土菜", "烧烤"],
        "patterns": [
            r'(?:午餐|晚餐|早餐|吃饭|餐厅)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*元',
            r'(\d+(?:\.\d+)?)\s*元\s*(?:午餐|晚餐|早餐|吃饭|餐厅)',
            r'(?:人均|每人)\s*[:：]?\s*(\d+(?:\.\d+)?)',
            r'(\d+(?:\.\d+)?)\s*元\s*(?:\/|每)\s*人(?:均)?',
        ]
    },
}


def extract_costs(text: str, context_tags: Optional[List[str]] = None) -> Dict[str, Any]:
    """从文本中智能提取费用

    返回 {
        'fuel_cost': 0, 'toll_cost': 0, 'accommodation_cost': 0,
        'food_cost': 0, 'ticket_cost': 0, 'parking_cost': 0,
        'other_cost': 0, 'per_person': None,
        'matches': [{'category': str, 'amount': float, 'evidence': str}, ...]
    }
    """
    result = {
        "fuel_cost": 0.0, "toll_cost": 0.0, "accommodation_cost": 0.0,
        "food_cost": 0.0, "ticket_cost": 0.0, "parking_cost": 0.0,
        "other_cost": 0.0, "per_person": None,
        "matches": [],
    }
    if not text:
        return result
    context_tags = context_tags or []
    used_amount_spans: List[Tuple[int, int]] = []

    def _is_span_used(start: int, end: int, exclude_per_person: bool = False) -> bool:
        for us, ue in used_amount_spans:
            if not (end <= us or start >= ue):
                return True
        return False

    for category, rule in COST_CATEGORY_RULES.items():
        matched_amounts = []
        evidence = []
        used_for_this = []
        for pattern in rule["patterns"]:
            for m in re.finditer(pattern, text):
                try:
                    amt = float(m.group(1))
                    amt_span = m.span(1)
                    if _is_span_used(*amt_span):
                        continue
                    matched_amounts.append(amt)
                    evidence.append(m.group(0))
                    used_for_this.append(amt_span)
                except (ValueError, IndexError):
                    continue
        if not matched_amounts:
            for kw in rule["keywords"]:
                kw_idx = text.find(kw)
                if kw_idx < 0:
                    continue
                window_start = max(0, kw_idx - 12)
                window_end = min(len(text), kw_idx + len(kw) + 12)
                window = text[window_start:window_end]
                near_match = re.search(r'(\d+(?:\.\d+)?)\s*元', window)
                if near_match:
                    amt = float(near_match.group(1))
                    abs_span = (window_start + near_match.span(1)[0],
                                window_start + near_match.span(1)[1])
                    if _is_span_used(*abs_span):
                        continue
                    matched_amounts.append(amt)
                    evidence.append(f"{kw}: {near_match.group(0)}")
                    used_for_this.append(abs_span)
                    break
        if matched_amounts:
            amount = max(matched_amounts)
            result[category] = round(amount, 2)
            result["matches"].append({
                "category": category,
                "amount": amount,
                "evidence": evidence[0],
            })
            for span in used_for_this:
                used_amount_spans.append(span)

    generic_amounts = []
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*元', text):
        amt = float(m.group(1))
        if amt <= 0:
            continue
        if _is_span_used(m.span(1)[0], m.span(1)[1]):
            continue
        matched = False
        for rec in result["matches"]:
            if f"{int(amt) if amt == int(amt) else amt}元" in rec["evidence"] or m.group(0) in rec["evidence"]:
                matched = True
                break
        if not matched:
            generic_amounts.append(amt)
    if generic_amounts and not any(
        result[k] for k in ["fuel_cost", "toll_cost", "accommodation_cost",
                            "food_cost", "ticket_cost", "parking_cost"]
    ):
        result["other_cost"] = round(max(generic_amounts), 2)
        result["matches"].append({
            "category": "other_cost",
            "amount": result["other_cost"],
            "evidence": f"通用金额: {max(generic_amounts)}元",
        })

    tag_category_map = {
        "加油": "fuel_cost", "油费": "fuel_cost",
        "住宿": "accommodation_cost", "酒店": "accommodation_cost", "民宿": "accommodation_cost",
        "午餐": "food_cost", "晚餐": "food_cost", "餐饮": "food_cost",
        "门票": "ticket_cost", "景区": "ticket_cost",
        "过路费": "toll_cost", "高速": "toll_cost",
        "停车": "parking_cost",
    }
    for tag in context_tags:
        if tag in tag_category_map and result[tag_category_map[tag]] == 0:
            for m in re.finditer(r'(\d+(?:\.\d+)?)', text):
                try:
                    amt = float(m.group(1))
                    if 10 <= amt <= 100000 and not _is_span_used(m.span(1)[0], m.span(1)[1]):
                        result[tag_category_map[tag]] = round(amt, 2)
                        result["matches"].append({
                            "category": tag_category_map[tag],
                            "amount": amt,
                            "evidence": f"#{tag} 关联金额: {amt}",
                        })
                        used_amount_spans.append(m.span(1))
                        break
                except ValueError:
                    continue

    if result["per_person"] is None:
        per_person_m = re.search(r'(?:人均|每人)\s*[:：]?\s*(\d+(?:\.\d+)?)', text)
        if per_person_m:
            result["per_person"] = float(per_person_m.group(1))

    return result


def cost_breakdown_to_fields(costs: Dict[str, Any]) -> Dict[str, float]:
    """把 extract_costs 结果映射到 RoadEvent 字段
    说明：RoadEvent 的数值字段只存 fuel/toll/other，细项由 cost_breakdown 提供更详细的分类。other_cost 仅包含真正的杂项（未分类的其他费用。"""
    return {
        "fuel_cost": costs.get("fuel_cost", 0.0),
        "toll_cost": costs.get("toll_cost", 0.0),
        "other_cost": round(costs.get("other_cost", 0.0), 2),
        "_breakdown": {
            "accommodation": costs.get("accommodation_cost", 0.0),
            "food": costs.get("food_cost", 0.0),
            "ticket": costs.get("ticket_cost", 0.0),
            "parking": costs.get("parking_cost", 0.0),
            "other": costs.get("other_cost", 0.0),
            "per_person": costs.get("per_person"),
        }
    }


# ---------------------------------------------------------------------------
# 累计里程时间轴 - 供 orphan 事件回溯
# ---------------------------------------------------------------------------

def build_mileage_timeline(segments: List[Dict[str, Any]]) -> List[Tuple[datetime, float]]:
    """根据所有 driving 段构建 (时间点, 累计里程) 时间轴"""
    timeline = []
    cumulative = 0.0
    for seg in segments:
        if seg.get("type") == "driving":
            cumulative += seg.get("distance", 0.0)
            if seg.get("end_time"):
                timeline.append((seg["end_time"], round(cumulative, 2)))
        else:
            if seg.get("start_time") and timeline:
                timeline.append((seg["start_time"], timeline[-1][1]))
            if seg.get("end_time") and timeline:
                timeline.append((seg["end_time"], timeline[-1][1]))
    return timeline


def lookup_cumulative_mileage(timeline: List[Tuple[datetime, float]],
                              query_time: Optional[datetime]) -> float:
    """根据时间点回溯当时的累计里程"""
    if not timeline or query_time is None:
        return 0.0
    if query_time <= timeline[0][0]:
        return 0.0
    if query_time >= timeline[-1][0]:
        return timeline[-1][1]
    for i in range(1, len(timeline)):
        t_prev, km_prev = timeline[i - 1]
        t_curr, km_curr = timeline[i]
        if t_prev <= query_time <= t_curr:
            delta_t = (t_curr - t_prev).total_seconds()
            if delta_t <= 0:
                return km_prev
            ratio = (query_time - t_prev).total_seconds() / delta_t
            return round(km_prev + (km_curr - km_prev) * ratio, 2)
    return timeline[-1][1]


# ---------------------------------------------------------------------------
# 文本分类辅助（避坑模板用）
# ---------------------------------------------------------------------------

def categorize_pitfall(text: str) -> str:
    """把一条踩坑文本归类为：费用 / 路况 / 住宿 / 餐饮 / 拍照 / 其他"""
    if any(k in text for k in ["坑", "贵", "宰", "元", "门票", "乱收费", "价格", "人均", "消费", "收费"]):
        for fw in ["路", "堵", "修", "封", "限行", "塌方", "落石", "弯", "坡", "海拔", "盘山", "烂路"]:
            if fw in text:
                return "路况坑"
        for fw in ["酒店", "民宿", "住宿", "客栈", "房间", "隔音", "热水", "空调", "卫生", "停车"]:
            if fw in text:
                return "住宿坑"
        for fw in ["餐厅", "吃饭", "午餐", "晚餐", "餐馆", "味道", "分量", "卫生", "拉肚子", "拉客"]:
            if fw in text:
                return "餐饮坑"
        for fw in ["拍", "摄影", "相机", "镜头", "光线", "角度"]:
            if fw in text:
                return "拍照坑"
        return "费用坑"
    if any(k in text for k in ["路", "堵", "修", "封路", "限行", "塌方", "落石", "弯", "盘山", "烂路", "陷车"]):
        return "路况坑"
    if any(k in text for k in ["酒店", "民宿", "住宿", "客栈", "房间", "隔音", "热水", "空调", "卫生"]):
        return "住宿坑"
    if any(k in text for k in ["餐厅", "吃饭", "午餐", "晚餐", "味道", "分量", "不推荐"]):
        return "餐饮坑"
    if any(k in text for k in ["拍", "照", "摄影", "光线", "角度"]):
        return "拍照坑"
    return "其他坑"
