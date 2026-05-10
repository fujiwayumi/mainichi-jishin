#!/usr/bin/env python3
"""
【地震・防災コンテンツ 自動生成システム】
キャラ：AIナナ
テーマ：地震・防災・火山・都市伝説・過去の教訓など
投稿先：まいにち地震ウォッチ（WordPress REST API）
1日1〜2記事を自動生成・投稿
"""

import os
import json
import requests
import feedparser
import base64
import email.utils
import random
import re
from datetime import datetime, timezone, timedelta

# ===================================================
# ⚙️ 設定
# ===================================================
WP_URL         = os.environ.get("EQ_WP_URL", "https://mainichi-jishin.com")
WP_USER        = os.environ.get("EQ_WP_USER", "")
WP_PASSWORD    = os.environ.get("EQ_WP_PASSWORD", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
AMAZON_TAG     = os.environ.get("AMAZON_TAG", "your-tag-22")

# ===================================================
# 🎭 AIナナ キャラクタープロンプト
# ===================================================
NANA_CHARACTER_PROMPT = """
あなたは「AIナナ」という名前のAIキャラクターです。
「まいにち地震ウォッチ」というブログで、地震・防災・火山・都市伝説などの情報を届けています。

【基本属性】
- 冒頭の挨拶：必ず「AIナナです」と名乗ることから始める
- 性格：冷静・的確・でも最後にひとこと優しい
- 口調：「〜です」「〜でしょう」「〜してください」。ときどき「備えがあれば怖くない。」
- 得意：地震・防災・火山・災害の科学的解説
- スタンス：科学的事実を大切にしつつ、地震雲・人工地震・都市伝説も「信じるかどうかは読者が判断して」というフラットな姿勢で紹介する

【文体・語調】
- 難しい言葉はわかりやすく言い換える
- 煽らない・怖がらせすぎない。でも必要な情報は明確に伝える
- 記事の最後は必ず「だから今できること」または「ナナからひとこと」で締める
- 「本記事では〜について解説します」のような書き出しは禁止
- 「〜です。〜ます。」だけの硬い文体は禁止

【Cocoon吹き出しの使い方】
以下のHTMLをそのまま使う（中身のテキストだけ変える）：

<div class="speech-wrap sb-id-1 sbs-stn sbp-l sbis-cb cf">
<div class="speech-person">
<figure class="speech-icon"><img class="speech-icon-image" src="https://mainichi-jishin.com/wp-content/uploads/2026/04/nana.png" alt="AIナナ" width="100" height="100" /></figure>
<div class="speech-name">AIナナ</div>
</div>
<div class="speech-balloon">
ここにテキストを入れる
</div>
</div>

使う場所は必ず2箇所：
① 冒頭の挨拶（「AIナナです。今日は〜についてお伝えします。」など）
② 最後の締め（「だから今できること」または「ナナからひとこと」）

【記事の構成ルール】
1. 冒頭：Cocoon吹き出しで挨拶
2. H2見出し4〜5個で構成
3. 重要なデータ・数字は必ず入れる
4. Amazonアフィリエイトリンクを2〜3個自然に挿入
5. 参照元：記事末尾に【参照情報】としてURLをHTMLリスト形式で記載
6. AI開示：「※この記事はAIキャラ・ナナが最新情報をもとに自動生成しました。」を記載
7. 締め：Cocoon吹き出しで「ナナからひとこと」

【オカルト・都市伝説テーマの書き方】
- 地震雲・人工地震・前兆現象などは「科学的には証明されていませんが、こういう説があります」というスタンスで紹介
- 否定もしない・肯定もしない。読者が自分で判断できるよう情報を整理する
- 最後に「科学的に確実なのは備えること」でまとめる

【禁止事項】
- Markdown記法（**太字**など）は絶対に使わない
- 強調したい部分は <strong>テキスト</strong> のHTMLタグを使う
- 人間のふりをした表現（AIキャラとして堂々と振る舞う）
- 過度な煽り・不安をあおりすぎる表現
"""

# ===================================================
# 🎬 YouTube動画リスト（テーマ別・公式チャンネル）
# ===================================================
YOUTUBE_VIDEOS = {
    "bousai": [
        {"id": "qgjZHORXf50", "title": "南海トラフ地震対策編・全体版（内閣府防災）"},
        {"id": "t0V0kEroyjk", "title": "大規模地震時における電気火災対策編（内閣府）"},
        {"id": "K5bYG3Z-8Jc", "title": "南海トラフ巨大地震シミュレーション M9.1・震度7・大津波"},
    ],
    "kyoukun": [
        {"id": "4Sz9HrDS6W0", "title": "南海トラフ地震臨時情報に込められた教訓（テレビ朝日）"},
        {"id": "AjlbQiUkDU4", "title": "南海トラフ巨大地震（内閣府防災）"},
        {"id": "K5bYG3Z-8Jc", "title": "南海トラフ巨大地震シミュレーション M9.1・震度7・大津波"},
    ],
    "kazan": [
        {"id": "qgjZHORXf50", "title": "南海トラフ地震対策編・全体版（内閣府防災）"},
        {"id": "t0V0kEroyjk", "title": "大規模地震時における電気火災対策編（内閣府）"},
    ],
    "kagaku": [
        {"id": "qgjZHORXf50", "title": "南海トラフ地震対策編・全体版（内閣府防災）"},
        {"id": "AjlbQiUkDU4", "title": "南海トラフ巨大地震（内閣府防災）"},
        {"id": "4Sz9HrDS6W0", "title": "南海トラフ地震臨時情報に込められた教訓（テレビ朝日）"},
        {"id": "K5bYG3Z-8Jc", "title": "南海トラフ巨大地震シミュレーション M9.1・震度7・大津波"},
    ],
    "occult": [
        {"id": "VTb0wvjMYlc", "title": "2025年7月5日に大災難は本当か？防災視点の詳細解説（そなえるTV）"},
        {"id": "K5bYG3Z-8Jc", "title": "南海トラフ巨大地震シミュレーション M9.1・震度7・大津波"},
    ],
    "kaigai": [
        {"id": "AjlbQiUkDU4", "title": "南海トラフ巨大地震（内閣府防災）"},
        {"id": "qgjZHORXf50", "title": "南海トラフ地震対策編・全体版（内閣府防災）"},
    ],
}


def build_youtube_section(theme_id: str) -> str:
    """テーマに合わせたYouTube動画セクションHTMLを生成"""
    videos = YOUTUBE_VIDEOS.get(theme_id, [])
    if not videos:
        return ""

    # 最大2本をランダムに選ぶ
    picked = random.sample(videos, min(2, len(videos)))

    html = '<h2>🎬 関連動画</h2>\n'
    for video in picked:
        vid_id = video["id"]
        title  = video["title"]
        html += (
            f'<div style="margin:20px 0;">\n'
            f'<p style="font-weight:bold;margin-bottom:8px;">{title}</p>\n'
            f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;">\n'
            f'<iframe style="position:absolute;top:0;left:0;width:100%;height:100%;" '
            f'src="https://www.youtube.com/embed/{vid_id}" '
            f'title="{title}" frameborder="0" '
            f'allow="accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture" '
            f'allowfullscreen loading="lazy"></iframe>\n'
            f'</div>\n'
            f'</div>\n'
        )
    return html


# ===================================================
# 🎯 テーマ定義
# ===================================================
THEMES = [
    {
        "id":          "bousai",
        "theme":       "防災・備蓄・自治体の最新情報",
        "category_id": 31,
        "keywords": [
            "防災", "備蓄", "避難", "ハザードマップ", "自治体", "防災訓練",
            "非常食", "備え", "避難所", "防災グッズ", "緊急速報",
            "disaster", "evacuation", "emergency", "preparedness",
        ],
        "context": "自治体・国の最新防災情報や備蓄の方法をナナ目線で解説する。具体的な準備リストや最新の推奨備蓄量も紹介する。",
        "amazon_items": [
            ("防災セット 家族4人用", "防災セット+家族+4人用"),
            ("保存水 2L 24本 5年保存", "保存水+2L+24本"),
            ("非常食 7日分 セット", "非常食+7日分+セット"),
            ("ポータブル電源 大容量 防災", "ポータブル電源+防災"),
            ("防災ラジオ 手回し充電", "防災ラジオ+手回し充電"),
            ("避難リュック 非常用持ち出し袋", "避難リュック+非常用持ち出し袋"),
            ("耐震マット 家具転倒防止", "耐震マット+家具転倒防止"),
            ("携帯トイレ 防災", "携帯トイレ+防災"),
        ],
    },
    {
        "id":          "kyoukun",
        "theme":       "過去の地震・津波・災害の教訓",
        "category_id": 32,
        "keywords": [
            "阪神淡路", "東日本大震災", "熊本地震", "能登", "関東大震災",
            "津波", "液状化", "震災", "復興", "教訓", "被害",
            "1995", "2011", "2016", "magnitude", "tsunami", "earthquake history",
        ],
        "context": "過去の大地震・津波・災害の具体的な数字・教訓を掘り下げ、現代の備えに活かせる情報をナナが解説する。",
        "amazon_items": [
            ("防災 窓ガラス 飛散防止フィルム", "防災+窓ガラス+飛散防止フィルム"),
            ("耐震ジェル 防振マット", "耐震ジェル+防振マット"),
            ("救急セット 家庭用", "救急セット+家庭用"),
            ("防災 本 備え", "防災+本+備え"),
            ("地震 絵本 子供", "地震+絵本+子供"),
            ("保存水 500ml 48本", "保存水+500ml+48本"),
        ],
    },
    {
        "id":          "kazan",
        "theme":       "火山・噴火・地質異常",
        "category_id": 33,
        "keywords": [
            "火山", "噴火", "富士山", "桜島", "阿蘇", "草津", "溶岩",
            "火砕流", "降灰", "噴煙", "活火山", "警戒レベル",
            "volcano", "eruption", "lava", "ash", "magma",
        ],
        "context": "火山活動・噴火情報と日常生活への影響をナナが解説する。富士山噴火の可能性や降灰対策なども扱う。",
        "amazon_items": [
            ("防塵マスク 火山灰 対策", "防塵マスク+火山灰"),
            ("ゴーグル 防塵 防災", "ゴーグル+防塵+防災"),
            ("非常食 缶詰 長期保存", "非常食+缶詰+長期保存"),
            ("防災ラジオ 手回し充電", "防災ラジオ+手回し充電"),
            ("ポータブル電源 大容量 防災", "ポータブル電源+防災"),
        ],
    },
    {
        "id":          "kagaku",
        "theme":       "地震科学・南海トラフ・活断層・予知",
        "category_id": 34,
        "keywords": [
            "南海トラフ", "首都直下", "活断層", "地震予知", "地震計",
            "プレート", "震源", "マグニチュード", "震度", "地震波",
            "seismic", "fault", "plate", "prediction", "Nankai",
        ],
        "context": "地震のメカニズム・南海トラフ・活断層の最新研究をナナがわかりやすく解説する。専門用語はかみ砕いて伝える。",
        "amazon_items": [
            ("南海トラフ 本 地震", "南海トラフ+本+地震"),
            ("地震 防災 入門 本", "地震+防災+入門+本"),
            ("防災セット 家族用", "防災セット+家族用"),
            ("保存水 2L 24本", "保存水+2L+24本"),
            ("非常食 アルファ米 セット", "非常食+アルファ米+セット"),
        ],
    },
    {
        "id":          "occult",
        "theme":       "地震雲・人工地震・前兆現象・都市伝説",
        "category_id": 35,
        "keywords": [
            "地震雲", "人工地震", "前兆", "予言", "HAARP", "電磁波",
            "動物の異常行動", "地鳴り", "発光現象", "地震予知",
            "earthquake cloud", "HAARP", "precursor", "prediction",
        ],
        "context": """地震雲・人工地震・前兆現象・都市伝説をフラットな視点で紹介する。
科学的には証明されていないが「こういう説がある」という姿勢で解説し、
最後は「科学的に確実なのは備えること」でまとめる。""",
        "amazon_items": [
            ("地震 前兆 本", "地震+前兆+本"),
            ("防災 備え 入門", "防災+備え+入門"),
            ("保存水 防災", "保存水+防災"),
            ("非常食 セット", "非常食+セット"),
        ],
    },
    {
        "id":          "kaigai",
        "theme":       "世界の大地震・海外の防災事情",
        "category_id": 3,
        "keywords": [
            "世界", "海外", "トルコ", "チリ", "インドネシア", "ネパール",
            "モロッコ", "アフガニスタン", "津波", "世界遺産", "復興",
            "world earthquake", "global disaster", "international",
        ],
        "context": "世界各地の大地震・防災の取り組みをナナが紹介する。日本との比較・日本人が学べる教訓も含める。",
        "amazon_items": [
            ("防災 世界 本", "防災+世界+本"),
            ("非常食 長期保存", "非常食+長期保存"),
            ("ポータブル電源 防災", "ポータブル電源+防災"),
            ("防災セット 家族", "防災セット+家族"),
        ],
    },
]

# ===================================================
# 📡 RSSフィード
# ===================================================
RSS_FEEDS = [
    {"url": "https://www3.nhk.or.jp/rss/news/cat1.xml",          "label": "NHK 社会"},
    {"url": "https://www3.nhk.or.jp/rss/news/cat3.xml",          "label": "NHK 科学・医療"},
    {"url": "https://www.jma.go.jp/bosai/info/rss/regular.xml",  "label": "気象庁 防災情報"},
    {"url": "https://news.google.com/rss/search?q=when:48h+地震+防災+津波+火山+震災&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "防災ニュース"},
    {"url": "https://news.google.com/rss/search?q=when:48h+南海トラフ+首都直下+活断層+地震予知&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "地震科学ニュース"},
    {"url": "https://news.google.com/rss/search?q=when:48h+火山+噴火+富士山+桜島&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "火山ニュース"},
    {"url": "https://news.google.com/rss/search?q=when:48h+地震雲+人工地震+前兆+予言&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "地震雲・都市伝説"},
    {"url": "https://news.google.com/rss/search?q=when:48h+(earthquake+OR+tsunami+OR+volcano+OR+disaster)&ceid=US:en&hl=en-US&gl=US",
                                                                  "label": "海外地震・災害"},
    {"url": "https://news.google.com/rss/search?q=when:48h+防災+備蓄+自治体+避難&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "防災・自治体情報"},
]

# ===================================================
# 🧠 メモリ管理
# ===================================================
MEMORY_FILE = "content_memory.json"


def load_memory() -> dict:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"published_titles": [], "published_topics": [], "last_updated": ""}


def save_memory(memory: dict):
    memory["last_updated"] = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")
    memory["published_titles"] = memory["published_titles"][-100:]
    memory["published_topics"] = memory["published_topics"][-50:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


# ===================================================
# 📰 ニュース収集
# ===================================================
def parse_rss_date(entry) -> datetime:
    for field in ["published", "updated"]:
        val = entry.get(field, "")
        if val:
            try:
                t = email.utils.parsedate_to_datetime(val)
                return t.astimezone(timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def fetch_all_news(hours: int = 48) -> list[dict]:
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_news = []

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:20]:
                pub = parse_rss_date(entry)
                if pub < cutoff:
                    continue
                all_news.append({
                    "title":     entry.get("title", ""),
                    "summary":   entry.get("summary", "")[:300],
                    "link":      entry.get("link", ""),
                    "published": pub.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
                    "source":    feed_info["label"],
                })
        except Exception as e:
            print(f"  → RSS取得エラー ({feed_info['label']}): {e}")

    # 重複タイトルを除去
    seen, unique = set(), []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    print(f"  → ニュース取得: {len(unique)}件")
    return unique


# ===================================================
# 🎯 テーマ自動選択
# ===================================================
def select_best_theme(news_list: list, memory: dict) -> dict:
    scores = {t["id"]: 0 for t in THEMES}

    for item in news_list:
        text = item["title"] + " " + item["summary"]
        for theme in THEMES:
            if any(kw in text for kw in theme["keywords"]):
                scores[theme["id"]] += 1

    # 直前と同じテーマを除外
    recent_topics = memory.get("published_topics", [])
    if recent_topics:
        last = recent_topics[-1]
        scores[last] = -999

    # 直近3件で2回以上使ったテーマにペナルティ
    for theme in THEMES:
        tid = theme["id"]
        recent_3 = recent_topics[-3:]
        if recent_3.count(tid) >= 2:
            scores[tid] -= 10

    print(f"  → テーマスコア: { {k: round(v,1) for k,v in scores.items()} }")
    best_id = max(scores, key=lambda k: scores[k])

    if scores[best_id] <= 0:
        unused = [t for t in THEMES if t["id"] not in recent_topics[-3:]]
        selected = random.choice(unused if unused else THEMES)
        print(f"  → スコアなし → ランダム選択: {selected['theme']}")
        return selected

    result = next(t for t in THEMES if t["id"] == best_id)
    print(f"  → 選択テーマ: {result['theme']}（スコア: {scores[best_id]}）")
    return result


def filter_news_by_theme(news_list: list, theme: dict) -> list:
    filtered = [
        item for item in news_list
        if any(kw in item["title"] + " " + item["summary"] for kw in theme["keywords"])
    ]
    return filtered[:8] if filtered else news_list[:5]


# ===================================================
# ✍️ 記事生成（Claude API）
# ===================================================
def generate_article(news_items: list, theme_info: dict, memory: dict) -> dict:
    news_text = "\n".join([
        f"・{item['title']}（{item['published']}）\n  {item['summary']}\n  URL: {item['link']}\n  出典: {item['source']}"
        for item in news_items
    ])

    amazon_items = theme_info["amazon_items"]
    amazon_pick  = random.sample(amazon_items, min(3, len(amazon_items)))
    amazon_examples = "\n".join([
        f'  例：<a href="https://www.amazon.co.jp/s?k={kw}&tag={AMAZON_TAG}" target="_blank" rel="noopener sponsored">{label}</a>'
        for label, kw in amazon_pick
    ])

    past_titles = memory.get("published_titles", [])
    past_str = "\n".join([f"・{t}" for t in past_titles[-20:]]) if past_titles else "なし"

    jst_now   = datetime.now(timezone(timedelta(hours=9)))
    post_date = jst_now.strftime("%Y.%-m.%-d")

    user_prompt = f"""
今日のテーマ：「{theme_info['theme']}」
記事の方向性：{theme_info['context']}

以下の直近48時間のニュースをもとに、WordPressブログ記事を書いてください。

【最新ニュース】
{news_text}

【記事の要件】
- 文字数：1,500〜2,500文字
- タイトル：クリックしたくなる表現にする
  ・タイトルの冒頭または末尾に投稿日付を入れる
    形式：「【{post_date}】〜」または「〜（{post_date}時点）」
- 見出し（H2）を4〜5個つける
- Amazonアフィリエイトリンクを2〜3個挿入する：
{amazon_examples}
- ニュースを引用した箇所には必ずインラインリンクを貼る
  形式：<a href="引用元URL" target="_blank" rel="noopener">記事タイトル</a>
- 記事末尾に【参照情報】としてURLをHTMLリスト形式で記載
- 記事末尾に「※この記事はAIキャラ・ナナが最新情報をもとに自動生成しました。情報は公開時点のものです。」を記載

【過去に投稿済みのタイトル（重複・類似を避けること）】
{past_str}

【出力形式】
JSON形式のみで出力してください（マークダウン記法・コードブロックは不要）：
{{
  "title": "記事タイトル",
  "slug": "japanese-content-slug（英語30文字以内）",
  "content": "記事本文（HTML形式、h2タグ使用、Markdown記法禁止）",
  "excerpt": "記事の概要（100文字程度）",
  "tags": ["タグ1", "タグ2", "タグ3"]
}}
"""

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         CLAUDE_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model":   "claude-sonnet-4-20250514",
            "max_tokens": 8000,
            "system":  NANA_CHARACTER_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        },
        timeout=120,
    )
    response.raise_for_status()
    raw = response.json()["content"][0]["text"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        article = json.loads(raw)
    except json.JSONDecodeError:
        print("  → JSONパースエラー。修復を試みます...")
        title_m   = re.search(r'"title"\s*:\s*"([^"]+)"', raw)
        slug_m    = re.search(r'"slug"\s*:\s*"([^"]+)"', raw)
        excerpt_m = re.search(r'"excerpt"\s*:\s*"([^"]+)"', raw)
        article = {
            "title":   title_m.group(1) if title_m else "本日の記事",
            "slug":    slug_m.group(1) if slug_m else "post",
            "content": "<p>※記事生成中にエラーが発生しました。</p>",
            "excerpt": excerpt_m.group(1) if excerpt_m else "",
            "tags":    [],
        }

    # Markdown太字をHTMLに変換
    content = article.get("content", "")
    content = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', content)

    # YouTubeセクションを記事末尾（参照情報の直前）に挿入
    youtube_html = build_youtube_section(theme_info["id"])
    if youtube_html:
        # 【参照情報】の直前に挿入
        if "【参照情報】" in content:
            content = content.replace("【参照情報】", youtube_html + "\n<h2>【参照情報】</h2>\n", 1)
        elif "参照情報" in content:
            content = content.replace("参照情報", youtube_html + "\n<h2>参照情報</h2>\n", 1)
        else:
            # 見つからない場合は末尾に追加
            content += "\n" + youtube_html

    article["content"] = content

    return article


# ===================================================
# 🎨 アイキャッチSVG生成
# ===================================================
THEME_COLORS = {
    "bousai":  {"bg": "#1565C0", "accent": "#BBDEFB", "icon": "🛡️", "label": "防災・備蓄"},
    "kyoukun": {"bg": "#4E342E", "accent": "#FFCCBC", "icon": "📖", "label": "災害の教訓"},
    "kazan":   {"bg": "#BF360C", "accent": "#FFCCBC", "icon": "🌋", "label": "火山・噴火"},
    "kagaku":  {"bg": "#1B5E20", "accent": "#C8E6C9", "icon": "🔬", "label": "地震科学"},
    "occult":  {"bg": "#4A148C", "accent": "#E1BEE7", "icon": "🌀", "label": "都市伝説"},
    "kaigai":  {"bg": "#006064", "accent": "#B2EBF2", "icon": "🌏", "label": "海外の地震"},
}

SITE_NAME    = "まいにち地震ウォッチ"
SITE_TAGLINE = "日本の揺れを、毎日記録する。"


def _esc(text: str) -> str:
    return (str(text)
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def generate_content_eyecatch(theme_id: str, title: str) -> str:
    """コンテンツ記事用アイキャッチSVGを生成"""
    c      = THEME_COLORS.get(theme_id, {"bg": "#37474F", "accent": "#CFD8DC", "icon": "📰", "label": "防災情報"})
    bg     = c["bg"]
    accent = c["accent"]
    icon   = c["icon"]
    label  = c["label"]

    W, H    = 1200, 630
    jst_now = datetime.now(timezone(timedelta(hours=9)))
    date_str = jst_now.strftime("%Y.%m.%d")

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="auto" '        f'viewBox="0 0 {W} {H}" style="display:block;max-width:100%;">\n'
        f'  <defs>\n'
        f'    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">\n'
        f'      <stop offset="0%" stop-color="{bg}"/>\n'
        f'      <stop offset="100%" stop-color="{bg}CC"/>\n'
        f'    </linearGradient>\n'
        f'  </defs>\n'
        f'  <rect width="{W}" height="{H}" fill="url(#bg)"/>\n'
        f'  <circle cx="900" cy="400" r="320" fill="white" fill-opacity="0.05"/>\n'
        f'  <!-- ヘッダー -->\n'
        f'  <rect x="0" y="0" width="{W}" height="72" fill="#00000033"/>\n'
        f'  <text x="40" y="47" font-family="sans-serif" font-size="24" font-weight="bold" '        f'fill="white" opacity="0.9">🌏 {_esc(SITE_NAME)}</text>\n'
        f'  <!-- アイコン（中央大きく） -->\n'
        f'  <text x="50%" y="54%" font-family="sans-serif" font-size="200" '        f'text-anchor="middle" dominant-baseline="middle">{icon}</text>\n'
        f'  <!-- カテゴリラベル -->\n'
        f'  <rect x="50%" y="72%" width="320" height="52" rx="26" fill="white" '        f'fill-opacity="0.2" transform="translate(-160,0)"/>\n'
        f'  <text x="50%" y="77%" font-family="sans-serif" font-size="34" '        f'fill="white" text-anchor="middle" font-weight="bold">{label}</text>\n'
        f'  <!-- 日付 -->\n'
        f'  <text x="50%" y="88%" font-family="sans-serif" font-size="32" '        f'fill="{accent}" text-anchor="middle" opacity="0.9">{date_str}</text>\n'
        f'  <!-- フッター -->\n'
        f'  <rect x="0" y="{H - 58}" width="{W}" height="58" fill="#00000044"/>\n'
        f'  <text x="40" y="{H - 18}" font-family="sans-serif" font-size="20" '        f'fill="white" opacity="0.7">{_esc(SITE_TAGLINE)}</text>\n'
        f'</svg>'
    )

    return svg


def upload_svg_as_eyecatch(svg_str: str, slug: str, auth_header: str) -> int | None:
    filename  = f"content-{slug}.svg"
    svg_bytes = svg_str.encode("utf-8")
    try:
        res = requests.post(
            f"{WP_URL}/wp-json/wp/v2/media",
            headers={
                "Authorization":       auth_header,
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type":        "image/svg+xml",
            },
            data=svg_bytes,
            timeout=30,
        )
        if res.status_code in [200, 201]:
            media_id = res.json().get("id")
            print(f"  → アイキャッチアップロード成功: ID={media_id}")
            return media_id
        print(f"  → アイキャッチアップロード失敗({res.status_code})")
        return None
    except Exception as e:
        print(f"  → アイキャッチエラー: {e}")
        return None


# ===================================================
# 📝 WordPress投稿
# ===================================================
def post_to_wordpress(article: dict, theme_info: dict) -> dict | None:
    auth = "Basic " + base64.b64encode(
        f"{WP_USER}:{WP_PASSWORD}".encode()
    ).decode()
    headers = {
        "Authorization": auth,
        "Content-Type":  "application/json",
    }

    # アイキャッチ生成・アップロード
    eyecatch_id = None
    try:
        svg_str     = generate_content_eyecatch(theme_info["id"], article["title"])
        eyecatch_id = upload_svg_as_eyecatch(svg_str, article.get("slug", "post"), auth)
    except Exception as e:
        print(f"  → アイキャッチスキップ: {e}")

    # タグ作成
    tag_ids = get_or_create_tags(article.get("tags", []), headers)

    payload = {
        "title":      article["title"],
        "slug":       article.get("slug", ""),
        "content":    article["content"],
        "excerpt":    article.get("excerpt", ""),
        "status":     "publish",
        "categories": [theme_info["category_id"]],
        "tags":       tag_ids,
    }
    if eyecatch_id:
        payload["featured_media"] = eyecatch_id

    try:
        res = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            headers=headers, json=payload, timeout=30,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"  → WordPress投稿エラー: {e}")
        return None


def get_or_create_tags(tag_names: list, headers: dict) -> list:
    tag_ids = []
    for name in tag_names:
        try:
            res = requests.get(
                f"{WP_URL}/wp-json/wp/v2/tags",
                params={"search": name}, headers=headers, timeout=10,
            )
            if res.status_code == 200 and res.json():
                tag_ids.append(res.json()[0]["id"])
            else:
                res2 = requests.post(
                    f"{WP_URL}/wp-json/wp/v2/tags",
                    headers=headers, json={"name": name}, timeout=10,
                )
                if res2.status_code == 201:
                    tag_ids.append(res2.json()["id"])
        except Exception:
            pass
    return tag_ids


# ===================================================
# 🚀 メイン処理
# ===================================================
def main():
    jst_now = datetime.now(timezone(timedelta(hours=9)))
    print(f"[{jst_now.strftime('%Y-%m-%d %H:%M JST')}] コンテンツ記事生成開始")

    if not CLAUDE_API_KEY:
        print("❌ CLAUDE_API_KEY が設定されていません")
        return

    # メモリ読み込み
    memory = load_memory()

    # ニュース収集
    print("📰 ニュース収集中...")
    news_list = fetch_all_news(hours=48)

    # テーマ選択
    print("🎯 テーマ選択中...")
    theme_info = select_best_theme(news_list, memory)

    # テーマに関連するニュースを絞り込み
    news_filtered = filter_news_by_theme(news_list, theme_info)
    print(f"  → 関連ニュース: {len(news_filtered)}件")

    # 記事生成
    print("✍️  AIナナで記事生成中...")
    article = generate_article(news_filtered, theme_info, memory)
    print(f"  → タイトル: {article['title']}")

    # WordPress投稿
    print("📝 WordPress投稿中...")
    result = post_to_wordpress(article, theme_info)

    if result:
        print(f"  → 投稿成功！ ID:{result['id']} / {result.get('link','')}")
        memory["published_titles"].append(article["title"])
        memory["published_topics"].append(theme_info["id"])
        save_memory(memory)
        print("  → メモリ更新完了")
    else:
        print("  → 投稿失敗")


if __name__ == "__main__":
    main()
