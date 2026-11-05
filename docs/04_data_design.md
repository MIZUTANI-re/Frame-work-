# データ設計書

| 項目 | 内容 |
|---|---|
| 文書番号 | FW-04 |
| 版 | 1.0（本人レビュー待ち） |
| 更新日 | 2026-11-05 |
| 関連文書 | [機能設計書](02_functional_design.md)・[技術設計書](05_technical_design.md)・[フレームワーク設計書](06_framework_design.md) |

## 1. 全体のつながり
```
User ─< Enrollment >─ Course ─< Team ─< TeamMember >─ User
                                  │
                                  └─< Board ─< Note >─ Cluster
                                        │       │
                                        │       └─< Vote
                                        └─< Event（記録。どのテーブルの操作も残す）
```
`─<` は「1 対 多」。例：1 つの授業（Course）に班（Team）が複数ある。

## 2. テーブル
### User（利用者）
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| name | 文字列 | ログイン名を兼ねる。全体で重複不可 |
| role | `teacher` / `student` | |
| password_hash | 文字列 | argon2 のハッシュ。平文は持たない |
| created_at | 日時 | |

### Course（授業）
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| name | 文字列 | |
| teacher_id | → User | 担当教員 |
| invite_code | 文字列（6） | 重複不可 |
| created_at | 日時 | |

### Enrollment（授業への参加）
| 列 | 型 | 説明 |
|---|---|---|
| course_id | → Course | |
| user_id | → User | |
| joined_at | 日時 | |
（course_id, user_id）の組は重複不可。

### Team（班）
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| course_id | → Course | |
| name | 文字列 | |

### TeamMember（班のメンバー）
| 列 | 型 | 説明 |
|---|---|---|
| team_id | → Team | |
| user_id | → User | |
1 つの授業の中で、学生が入る班は 1 つだけ（アプリ側で確かめる）。

### Board（ボード）※ステップ 2
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| team_id | → Team | |
| framework_key | 文字列 | どの定義から作ったか。例 `swot` |
| chosen_by | `teacher` / `student` | 誰が選んだか。今は `teacher` だけ（D-008） |
| created_by | → User | |
| phase | 文字列 | 今のフェーズ。例 `individual` |
| phase_ends_at | 日時 / 空 | 個人ワークの終了予定。時間が来たらサーバーが公開にする |
| conclusion | 文章 / 空 | 班の結論 |
| created_at | 日時 | |

### Note（付箋）※ステップ 2
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| board_id | → Board | |
| author_id | → User | 作成者 |
| zone_key | 文字列 / 空 | ゾーン型のときの区画。例 `S` |
| x, y | 小数（0〜1） | 位置。2 軸型ではこれが軸の値になる |
| text | 文章 | |
| cluster_id | → Cluster / 空 | 所属するまとまり |
| created_at / updated_at | 日時 | |
| deleted_at | 日時 / 空 | 消しても行は残す（記録のため） |

### Cluster（まとまり）※ステップ 3
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| board_id | → Board | |
| label | 文字列 | 見出し |
| summary | 文章 / 空 | 要約（後で LLM が使う） |
| made_by_kind | `human` / `ai` | |
| created_by | → User / 空 | |

### Vote（投票）※ステップ 3
| 列 | 型 | 説明 |
|---|---|---|
| board_id | → Board | |
| user_id | → User | |
| target_kind | `note` / `cluster` | |
| target_id | 整数 | |

### Event（記録）※ステップ 1 から
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| at | 日時 | |
| actor_id | → User / 空 | 誰が（タイマーなどサーバーなら空） |
| course_id / team_id / board_id | 整数 / 空 | どこで |
| type | 文字列 | 何を。下の表 |
| payload | JSON | 細かい中身 |

追記だけ。書き換え・削除はしない（NFR-06）。

## 3. 記録の種類
| type | いつ | ステップ |
|---|---|---|
| `course.joined` | 学生が授業に参加した | 1 |
| `team.member_added` / `team.member_removed` | 班のメンバーが変わった | 1 |
| `board.created` | ボードを作った（framework_key・chosen_by） | 2 |
| `note.created` / `note.edited` / `note.moved` / `note.deleted` | 付箋の操作 | 2 |
| `phase.changed` | フェーズが変わった（誰が / タイマーで） | 3 |
| `cluster.created` / `cluster.renamed` | まとまりの操作 | 3 |
| `vote.cast` / `vote.removed` | 投票 | 3 |
| `conclusion.saved` | 結論を書いた | 3 |

## 4. DB に入れないもの
- **フレームワークの定義**：リポジトリの `app/frameworks/*.json` に置き、Git で管理する。教員が自作する機能を付けるときに DB へ移す。

## 改訂履歴
| 版 | 日付 | 内容 |
|---|---|---|
| 1.0 | 2026-11-05 | 概要設計 v0.2 からデータの部分を分けて作成。列・記録の種類を追加 |
