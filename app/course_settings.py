"""授業の設定（D-045）。設定の名前・既定値・説明をここ 1 か所にまとめる。
足すときは SETTINGS に 1 行足すだけ（画面は SETTINGS を見て作る）。いまは真偽（する / しない）だけ。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SettingDef:
    default: bool
    label: str
    description: str
    true_label: str = "する"
    false_label: str = "しない"


SETTINGS: dict[str, SettingDef] = {
    "share_outputs_across_teams": SettingDef(
        default=False,
        label="成果（まとめシート）を全班で共有する",
        description="「する」にすると、ほかの班のまとめシートも見られるようになります（効き目はステップ 5 で作ります。いまは保存されるだけです）。",
    ),
}


def get_setting(settings: dict | None, name: str) -> bool:
    """保存された設定から値を取る。保存されていなければ既定値。"""
    return bool((settings or {}).get(name, SETTINGS[name].default))


def effective_settings(settings: dict | None) -> dict[str, bool]:
    return {name: get_setting(settings, name) for name in SETTINGS}
