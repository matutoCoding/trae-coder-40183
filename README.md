# roadtrip_planner 路书编排工具

给自驾内容创作者和路线测评博主使用的命令行路书编排工具。

## 功能特性

- **素材导入 (import)**: 从目的地文件、GPS 轨迹、照片 EXIF、文字备注按时间顺序生成初版路书，自动归类早晨出发、观景台停留、午餐、堵车、住宿入住等事件
- **模板编排 (template)**: 支持攻略、测评、避坑三种内容口径清洗模板
- **多平台导出 (export)**: 生成公众号长文提纲、短视频分镜清单、可下载行程表

## 安装

```bash
pip install -e .
```

## 快速开始

```bash
# 1. 导入素材生成初版路书
roadtrip import \
  --destinations examples/destinations.md \
  --gps examples/gps/track.gpx \
  --photos examples/photos/ \
  --notes examples/notes.md \
  --output outputs/initial_roadbook.json

# 2. 应用模板编排（攻略/测评/避坑）
roadtrip template \
  --input outputs/initial_roadbook.json \
  --style guide \
  --output outputs/styled_roadbook.json

# 3. 多平台导出
roadtrip export \
  --input outputs/styled_roadbook.json \
  --formats wechat,video,schedule \
  --output outputs/
```

## 命令详解

### import 命令

| 参数 | 说明 | 必需 |
|------|------|------|
| `--destinations` | 目的地文件 (Markdown) | 是 |
| `--gps` | GPS 轨迹文件 (.gpx/.kml/.csv) | 是 |
| `--photos` | 照片目录（读取 EXIF 时间戳） | 否 |
| `--notes` | 文字备注文件 (Markdown/CSV) | 否 |
| `--output` | 输出初版路书 JSON 文件 | 是 |

### template 命令

| 参数 | 说明 | 必需 |
|------|------|------|
| `--input` | 初版路书 JSON | 是 |
| `--style` | 模板类型: guide/review/pitfalls | 是 |
| `--output` | 输出编排后路书 JSON | 是 |

**三种模板侧重：**
- `guide`（攻略）: 突出里程、油耗、费用、拍照点位
- `review`（测评）: 突出路况、驾驶感受、设施评分、时间成本
- `pitfalls`（避坑）: 突出踩坑提醒、危险路段、避坑建议、备选方案

### export 命令

| 参数 | 说明 | 必需 |
|------|------|------|
| `--input` | 编排后路书 JSON | 是 |
| `--formats` | 导出格式（逗号分隔）: wechat,video,schedule | 是 |
| `--output` | 输出目录 | 是 |

**导出格式：**
- `wechat`: 公众号长文提纲 (Markdown)
- `video`: 短视频分镜清单 (CSV)
- `schedule`: 可下载行程表 (HTML + CSV)
