"""命令行入口 - 三个子命令：import / template / export"""
import os
import sys
import json
import logging
from pathlib import Path

import click

from .models import Roadbook, TemplateStyle
from .importer import import_materials
from .templater import apply_template
from .exporter import export_roadbook
from .utils import ensure_dir


def _setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )


@click.group(help="自驾路书编排工具 Roadtrip Planner - 面向内容创作者的命令行路书工具",
               context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version="0.1.0", prog_name="roadtrip")
@click.option("-v", "--verbose", is_flag=True, help="显示调试日志")
def cli(verbose):
    _setup_logging(verbose)


# ---------------------------------------------------------------------------
# import 命令
# ---------------------------------------------------------------------------

@cli.command("import", help="导入素材并生成初版路书 (GPS轨迹+照片+目的地+备注 → JSON路书")
@click.option("--destinations", "-d", "destinations_file",
              type=click.Path(exists=False),
              help="目的地文件 (Markdown)，例如 --destinations ./dests.md")
@click.option("--gps", "-g", "gps_file",
              type=click.Path(exists=False),
              help="GPS轨迹文件 (.gpx/.csv)")
@click.option("--photos", "-p", "photos_dir",
              type=click.Path(exists=False),
              help="照片目录 (读取EXIF时间戳)")
@click.option("--notes", "-n", "notes_file",
              type=click.Path(exists=False),
              help="文字备注文件 (.md/.csv)")
@click.option("--output", "-o", "output_path",
              required=True,
              type=click.Path(),
              help="输出初版路书 JSON 路径")
@click.option("--title", "-t", help="自定义路书标题")
def import_cmd(destinations_file, gps_file, photos_dir, notes_file, output_path, title):
    click.echo("🚗 开始导入素材…")
    if not gps_file:
        click.echo("⚠ 未提供 GPS 文件：将仅根据其他素材（如需完整功能请补充 .gpx 或 .csv 轨迹")
    try:
        rb = import_materials(
            destinations_file or "",
            gps_file or "",
            photos_dir or "",
            notes_file or "",
        )
        if title:
            rb.title = title
        ensure_dir(os.path.dirname(output_path) or ".")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rb.to_json())
        click.echo(f"✅ 初版路书已生成：")
        click.echo(f"   📄 标题：{rb.title}")
        click.echo(f"   📅 {rb.start_date} → {rb.end_date}（共 {rb.total_days} 天）")
        click.echo(f"   🛣 总里程：{rb.total_distance_km:.1f} 公里")
        click.echo(f"   📍 目的地：{len(rb.destinations)} 个")
        click.echo(f"   📝 事件数：{sum(len(d.events) for d in rb.days)} 条")
        click.echo(f"   💾 保存至：{output_path}")
    except Exception as e:
        logging.exception("导入失败")
        raise click.ClickException(f"导入素材导入失败：{e}")


# ---------------------------------------------------------------------------
# template 命令
# ---------------------------------------------------------------------------

@cli.command("template", help="应用模板编排：攻略/测评/避坑三种口径清洗")
@click.option("--input", "-i", "input_path",
              required=True,
              type=click.Path(exists=True),
              help="初版路书 JSON")
@click.option("--style", "-s",
              required=True,
              type=click.Choice(["guide", "review", "pitfalls"], case_sensitive=False),
              help="模板类型：guide攻略 / review测评 / pitfalls避坑")
@click.option("--output", "-o", "output_path",
              required=True,
              type=click.Path(),
              help="输出编排后路书 JSON")
def template_cmd(input_path, style, output_path):
    click.echo(f"🎨 应用模板：{style.upper()} 模式…")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            rb = Roadbook.from_json(f.read())
        style_enum = TemplateStyle(style.lower())
        styled = apply_template(rb, style_enum)
        ensure_dir(os.path.dirname(output_path) or ".")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(styled.to_json())
        style_names = {
            TemplateStyle.GUIDE: "攻略版（突出里程/油耗/费用/拍照点）",
            TemplateStyle.REVIEW: "测评版（突出路况/评分/时间成本）",
            TemplateStyle.PITFALLS: "避坑版（突出踩坑/危险/建议）",
        }
        click.echo(f"✅ 模板编排完成：{style_names.get(style_enum, style)}")
        click.echo(f"   📄 新标题：{styled.title}")
        click.echo(f"   💾 保存至：{output_path}")
    except Exception as e:
        logging.exception("模板编排失败")
        raise click.ClickException(f"模板编排失败：{e}")


# ---------------------------------------------------------------------------
# export 命令
# ---------------------------------------------------------------------------

@cli.command("export", help="多平台导出：公众号/短视频/行程表")
@click.option("--input", "-i", "input_path",
              required=True,
              type=click.Path(exists=True),
              help="路书 JSON（初版或模板处理均可）")
@click.option("--formats", "-f", "formats_str",
              required=True,
              help="导出格式（逗号分隔）：wechat,video,schedule")
@click.option("--output", "-o", "output_dir",
              required=True,
              type=click.Path(),
              help="输出目录")
def export_cmd(input_path, formats_str, output_dir):
    formats = [s.strip() for s in formats_str.split(",") if s.strip()]
    click.echo(f"📤 开始导出：{', '.join(formats)} → {output_dir}")
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            rb = Roadbook.from_json(f.read())
        ensure_dir(output_dir)
        results = export_roadbook(rb, formats, output_dir)
        click.echo("✅ 导出完成：")
        for name, files in results.items():
            click.echo(f"\n📦 {name}：")
            for fp in files:
                click.echo(f"   → {fp}")
    except Exception as e:
        logging.exception("导出失败")
        raise click.ClickException(f"导出失败：{e}")


def main():
    try:
        cli(standalone_mode=True)
    except click.ClickException:
        raise
    except KeyboardInterrupt:
        click.echo("\n⚠ 用户中断")
        sys.exit(130)


if __name__ == "__main__":
    main()
