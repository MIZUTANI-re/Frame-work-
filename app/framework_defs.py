"""フレームワークの定義ファイル（app/frameworks/*.json）を読み込む（フレームワーク設計書 §2）。
仕様に合わないものがあれば FrameworkDefError で、起動を止める。"""
import json
import re
from pathlib import Path

from app.config import BASE_DIR

FRAMEWORKS_DIR = BASE_DIR / "app" / "frameworks"

BOARD_TYPES = ("zone", "axis")
PHASE_NAMES = {"individual": "個人ワーク", "reveal": "公開", "cluster": "まとめる",
               "vote": "投票", "conclusion": "結論"}
# 外せない進め方（D-023。個人で考える時間と公開は、同調を防ぐための柱）
LOCKED_PHASES = ("individual", "reveal")
PURPOSE_LABELS = {"ideate": "発想", "analyze": "分析", "organize": "整理", "decide": "決定",
                  "plan": "計画", "reflect": "振り返り", "discuss": "話し合い"}
THINKING_LABELS = {"diverge": "発散", "converge": "収束"}
META_KEYS = ("purpose", "thinking", "scenes", "group_size", "minutes", "difficulty",
             "good_for", "pairs_with", "description", "source")
KEY_PATTERN = re.compile(r"^[a-z_]+$")


class FrameworkDefError(Exception):
    """定義ファイルが仕様に合わない。"""


def _check(ok: bool, file: Path, message: str) -> None:
    if not ok:
        raise FrameworkDefError(f"{file.name}: {message}")


def _is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def validate_definition(data: dict, file: Path) -> None:
    """必須の項目だけ確かめる（作り込まない。D-046）。"""
    _check(isinstance(data, dict), file, "最上位が { } ではありません")
    for name in ("key", "name", "aliases", "tags", "yomi", "board_type", "phases", "meta"):
        _check(name in data, file, f"必須の項目 {name} がありません")
    _check(isinstance(data["key"], str) and KEY_PATTERN.match(data["key"]) is not None, file,
           "key は英小文字と _ だけです")
    _check(data["key"] == file.stem, file, f"key（{data['key']}）とファイル名が違います")
    _check(isinstance(data["name"], str) and data["name"], file, "name が空です")
    for name in ("aliases", "tags", "yomi"):
        _check(_is_str_list(data[name]), file, f"{name} は文字列の並びにしてください")
    _check(data["board_type"] in BOARD_TYPES, file, "board_type は zone か axis です")
    if data["board_type"] == "zone":
        _check(isinstance(data.get("layout"), dict), file, "zone には layout が必要です")
        zones = data.get("zones")
        _check(isinstance(zones, list) and zones, file, "zone には zones が必要です")
        for z in zones:
            _check(isinstance(z, dict) and all(k in z for k in ("key", "label", "hint")), file,
                   "zones の各区画に key・label・hint が必要です")
    else:
        axes = data.get("axes")
        _check(isinstance(axes, dict) and all(
            isinstance(axes.get(a), dict) and all(k in axes[a] for k in ("label", "low", "high"))
            for a in ("x", "y")), file, "axis には axes（x・y それぞれ label・low・high）が必要です")
        quads = data.get("quadrants")
        _check(isinstance(quads, list) and quads, file, "axis には quadrants が必要です")
        for q in quads:
            _check(isinstance(q, dict) and all(k in q for k in ("key", "label", "x", "y")), file,
                   "quadrants の各象限に key・label・x・y が必要です")
    phases = data["phases"]
    _check(isinstance(phases, list) and phases, file, "phases が空です")
    keys = [p.get("key") if isinstance(p, dict) else None for p in phases]
    _check(all(k in PHASE_NAMES for k in keys), file, "phases に知らない進め方があります")
    _check(len(set(keys)) == len(keys), file, "phases に同じ進め方が 2 回あります")
    _check(all(k in keys for k in LOCKED_PHASES), file, "phases には individual と reveal が必要です")
    meta = data["meta"]
    _check(isinstance(meta, dict), file, "meta が { } ではありません")
    for name in META_KEYS:
        _check(name in meta, file, f"meta に {name} がありません")
    _check(meta["purpose"] in PURPOSE_LABELS, file, "meta.purpose が知らない値です")
    _check(meta["thinking"] in THINKING_LABELS, file, "meta.thinking が知らない値です")


def load_frameworks(directory: Path = FRAMEWORKS_DIR) -> dict[str, dict]:
    """ディレクトリの *.json を全部読む。CATALOG_ORDER にあるものを先に、それ以外はファイル名の順に並べる。"""
    files = sorted(directory.glob("*.json"))
    if not files:
        raise FrameworkDefError(f"{directory} に定義ファイルがありません")
    loaded: dict[str, dict] = {}
    for file in files:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise FrameworkDefError(f"{file.name}: JSON として読めません（{e}）") from e
        validate_definition(data, file)
        loaded[data["key"]] = data
    order = [k for k in CATALOG_ORDER if k in loaded] + [k for k in loaded if k not in CATALOG_ORDER]
    return {k: loaded[k] for k in order}


# カタログの順（回数が同じときの並び。フレームワーク設計書 §5）
CATALOG_ORDER = ("brainstorm", "swot", "payoff_matrix")

# 起動のときに 1 回読む。仕様に合わなければ、ここで import が失敗して起動が止まる
FRAMEWORKS: dict[str, dict] = load_frameworks()
