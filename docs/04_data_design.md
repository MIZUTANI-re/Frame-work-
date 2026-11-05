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
                       │          │
                       └─< CourseFramework ─< Board   （授業で選んだものが、班ごとのボードになる）
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
| failed_logins | 整数 | 続けてまちがえた回数。成功したら 0 に戻す。足すときは DB の 1 回の更新で足す（同時に送られても数えもれないため）（D-029） |
| locked_until | 日時 / 空 | この時刻までログインできない（5 回まちがえたら 5 分）。教員が解ける（D-040） |
| session_version | 整数 | ログアウトで 1 つ上げる。Cookie の版と合わなければ無効。1 人に 1 つなので、1 台でログアウトすると、別のパソコンで開いている分も出る |
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
| course_id | → Course | 班の授業（「1 人 1 班」を DB で守るために持つ） |
| user_id | → User | |
（course_id, user_id）の組は重複不可。1 つの授業の中で、学生が入る班は 1 つだけ。ボタンの 2 度押しで 2 つの班に入らないよう、アプリだけでなく DB で守る（D-026）。

### CourseFramework（授業で選んだフレームワーク）※ステップ 2
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| course_id | → Course | |
| framework_key | 文字列 | どの定義か。例 `brainstorm` |
| phases | JSON | 使う進め方の key の並び。抜いたものは入らない。例 `["individual","reveal","cluster","conclusion"]`（D-023） |
| position | 整数 | 授業の流れの順番（D-032） |
| status | `waiting` / `active` / `done` | 流れの中で、まだ・今・終わり。先生の「次へ」で進む |
| started_at / ended_at | 日時 / 空 | |
| created_by | → User | 選んだ先生 |
| created_at | 日時 | |

「よく使われている順」（D-022）は、この表の行を `framework_key` ごとに数えて作る。

### Board（ボード）※ステップ 2
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| team_id | → Team | |
| course_framework_id | → CourseFramework | どの「授業で選んだもの」から配られたか（D-021） |
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
| source_note_id / source_cluster_id | 整数 / 空 | 前のボードから持ち込んだときの元（D-033） |
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

### TeamSummary（まとめシート）※ステップ 5
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| team_id / course_id | → Team / → Course | |
| sections | JSON | フレームワークごとの結論・票の多い意見 |
| final_text | 文章 | 班の最終の結論 |
| llm_slots | JSON | LLM が埋める枠。`{"summary": null, "clusters": null, "next_actions": null}`。今は全部空（D-035） |
| image_path | 文字列 / 空 | 確定のときに作った画像の場所（保存係の中の名前） |
| version | 整数 | 確定するたびに 1 つ上げる。前の版の行も消さない（D-031） |
| confirmed_by / confirmed_at | → User / 日時 | |

### ChatMessage（チャット）※ステップ 2
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| course_id | → Course | どの授業の準備の中の会話か |
| user_id | 整数 / 空 | 送った人。LLM の返事なら空 |
| role | `user` / `assistant` | `assistant` は今は「LLM はまだつながっていません」の決まった返事だけ |
| text | 文章 | |
| created_at | 日時 | |

### Event（記録）※ステップ 1 から
| 列 | 型 | 説明 |
|---|---|---|
| id | 整数 | |
| at | 日時 | |
| actor_id | 整数 / 空 | 誰が（タイマーなどサーバーなら空） |
| course_id / team_id / board_id | 整数 / 空 | どこで |
| type | 文字列 | 何を。下の表 |
| payload | JSON | 細かい中身。班の名前など、あとで読んで分かるための情報も入れる |

追記だけ。書き換え・削除はしない（NFR-06）。Event の列はどれも外部キーにしない。班などが消えても記録だけは残すため（D-025）。

## 2.1 日時の持ち方
- 日時はすべて UTC で持つ。SQLite と PostgreSQL で同じように扱えるよう、共通の型（`UTCDateTime`）を 1 つ作って全部の列で使う。読み出したときは必ず「UTC のタイムゾーン付き」になる（D-027）。
- 画面に出すときだけ、日本時間に直す。

## 3. 記録の種類
| type | いつ | ステップ |
|---|---|---|
| `course.joined` | 学生が授業に参加した | 1 |
| `team.created` / `team.renamed` | 班を作った・名前を変えた（payload に班の名前）。班は消さない（D-030） | 1 |
| `user.unlocked` | 教員がログインの止まりを解いた（D-040） | 1.5 |
| `team.member_added` / `team.member_removed` | 班のメンバーが変わった | 1 |
| `framework.selected` | 先生が授業でフレームワークを選んだ（framework_key・そのとき打っていた言葉・使う進め方） | 2 |
| `board.created` | ボードを作った（framework_key・chosen_by） | 2 |
| `note.created` / `note.edited` / `note.moved` / `note.deleted` | 付箋の操作 | 2 |
| `phase.changed` | フェーズが変わった（誰が / タイマーで） | 3 |
| `cluster.created` / `cluster.renamed` | まとまりの操作 | 3 |
| `vote.cast` / `vote.removed` | 投票 | 3 |
| `conclusion.saved` | 結論を書いた | 3 |
| `flow.advanced` | 先生が「次へ」を押した（どれからどれへ） | 3 |
| `note.carried` | 前のボードから付箋を持ち込んだ | 3 |
| `summary.confirmed` / `summary.image_saved` | まとめシートを確定した・画像を保存した | 5 |
| `chat.posted` | チャットに送った | 2 |

## 4. DB に入れないもの
- **フレームワークの定義**：リポジトリの `app/frameworks/*.json` に置き、Git で管理する。教員が自作する機能を付けるときに DB へ移す。

## 改訂履歴
| 版 | 日付 | 内容 |
|---|---|---|
| 1.0 | 2026-11-05 | 概要設計 v0.2 からデータの部分を分けて作成。列・記録の種類を追加 |
| 1.1 | 2026-11-05 | CourseFramework を追加。Board に course_framework_id、記録に framework.selected（D-021〜D-023） |
