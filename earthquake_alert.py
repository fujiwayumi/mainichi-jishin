#!/usr/bin/env python3
"""
【地震速報 自動投稿システム】
- 国内：気象庁防災XML → 震度4以上で即投稿
- 海外：USGS Earthquake API → M5以上で即投稿
- 重複防止：earthquake_memory.json で投稿済みIDを管理
- 投稿先：別WordPressサイト（REST API）
"""

import os
import json
import requests
import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

# ===================================================
# ⚙️ 設定（GitHub Secretsから取得）
# ===================================================
WP_URL      = os.environ.get("EQ_WP_URL", "https://mainichi-jishin.com")
WP_USER     = os.environ.get("EQ_WP_USER", "")
WP_PASSWORD = os.environ.get("EQ_WP_PASSWORD", "")

# 閾値
DOMESTIC_SHINDO_MIN = 4      # 国内：震度4以上
OVERSEAS_MAG_MIN    = 5.0    # 海外：M5.0以上

# カテゴリID（WordPressで事前に作成しておく）
CATEGORY_DOMESTIC = 2   # 国内地震
CATEGORY_OVERSEAS = 3   # 海外地震

# メモリファイル
MEMORY_FILE = "earthquake_memory.json"

# 気象庁 地震情報XML
JMA_QUAKE_URL ="https://api.p2pquake.net/v2/history?codes=551&limit=10"

# USGS API（過去1時間、M5以上）
USGS_API_URL = (
    "https://earthquake.usgs.gov/fdsnws/event/1/query"
    "?format=geojson&minmagnitude=5.0&limit=20&orderby=time"
)

# 震度の表記マップ
SHINDO_LABEL = {
    "1": "震度1", "2": "震度2", "3": "震度3",
    "4": "震度4",
    "5-": "震度5弱", "5+": "震度5強",
    "6-": "震度6弱", "6+": "震度6強",
    "7": "震度7",
}

SHINDO_ALERT = {
    "4":  "⚠️",
    "5-": "🚨", "5+": "🚨",
    "6-": "🆘", "6+": "🆘",
    "7":  "🆘",
}

# ===================================================
# 🌏 海外地名の日本語変換
# ===================================================
COUNTRY_JA = {
    "Philippines": "フィリピン", "Indonesia": "インドネシア",
    "Japan": "日本", "China": "中国", "Taiwan": "台湾",
    "Papua New Guinea": "パプアニューギニア",
    "Solomon Islands": "ソロモン諸島", "Vanuatu": "バヌアツ",
    "Fiji": "フィジー", "Tonga": "トンガ",
    "New Zealand": "ニュージーランド", "Australia": "オーストラリア",
    "Myanmar": "ミャンマー", "India": "インド", "Nepal": "ネパール",
    "Afghanistan": "アフガニスタン", "Pakistan": "パキスタン",
    "Iran": "イラン", "Turkey": "トルコ", "Turkiye": "トルコ",
    "Russia": "ロシア", "Kazakhstan": "カザフスタン",
    "Kyrgyzstan": "キルギス", "Tajikistan": "タジキスタン",
    "Chile": "チリ", "Peru": "ペルー", "Ecuador": "エクアドル",
    "Colombia": "コロンビア", "Venezuela": "ベネズエラ",
    "Mexico": "メキシコ", "Guatemala": "グアテマラ",
    "El Salvador": "エルサルバドル", "Nicaragua": "ニカラグア",
    "Costa Rica": "コスタリカ", "Panama": "パナマ",
    "Honduras": "ホンジュラス", "Argentina": "アルゼンチン",
    "Bolivia": "ボリビア", "Brazil": "ブラジル",
    "United States": "アメリカ", "Alaska": "アラスカ",
    "Hawaii": "ハワイ", "Canada": "カナダ",
    "Italy": "イタリア", "Greece": "ギリシャ",
    "Romania": "ルーマニア", "Portugal": "ポルトガル",
    "Algeria": "アルジェリア", "Morocco": "モロッコ",
    "Ethiopia": "エチオピア", "Tanzania": "タンザニア",
    "Fiji Islands": "フィジー諸島",
    "Kermadec Islands": "ケルマデック諸島",
    "Mariana Islands": "マリアナ諸島",
    "Ryukyu Islands": "琉球諸島",
    "Kuril Islands": "千島列島",
    "Aleutian Islands": "アリューシャン列島",
    "South Sandwich Islands": "サウスサンドウィッチ諸島",
    "Banda Sea": "バンダ海", "Celebes Sea": "セレベス海",
    "Philippine Sea": "フィリピン海",
    "Pacific-Antarctic Ridge": "太平洋南極海嶺",
    "Pacific Ocean": "太平洋", "Indian Ocean": "インド洋",
    "Atlantic Ocean": "大西洋",
    # 海嶺・海溝・その他
    "Indian-Antarctic Ridge": "インド洋南極海嶺",
    "Pacific-Antarctic Ridge": "太平洋南極海嶺",
    "Southeast Indian Ridge": "南東インド洋海嶺",
    "Mid-Indian Ridge": "中央インド洋海嶺",
    "Mid-Atlantic Ridge": "中央大西洋海嶺",
    "Reykjanes Ridge": "レイキャネス海嶺",
    "East Pacific Rise": "東太平洋海膨",
    "Juan de Fuca Ridge": "ファン・デ・フカ海嶺",
    "Macquarie Island": "マッコーリー島",
    "Prince Edward Islands": "プリンスエドワード諸島",
    "South Sandwich Islands": "サウスサンドウィッチ諸島",
    "South Georgia Island": "サウスジョージア島",
    "Ascension Island": "アセンション島",
    "Owen Fracture Zone": "オーウェン断裂帯",
    "Carlsberg Ridge": "カールスバーグ海嶺",
    "Scotia Sea": "スコシア海",
    "Weddell Sea": "ウェッデル海",
    "Ross Sea": "ロス海",
    "Timor Sea": "ティモール海",
    "Arafura Sea": "アラフラ海",
    "Coral Sea": "コーラル海",
    "Tasman Sea": "タスマン海",
}

DIRECTION_JA = {
    "N": "北", "S": "南", "E": "東", "W": "西",
    "NE": "北東", "NW": "北西", "SE": "南東", "SW": "南西",
    "NNE": "北北東", "NNW": "北北西", "SSE": "南南東", "SSW": "南南西",
    "ENE": "東北東", "ESE": "東南東", "WNW": "西北西", "WSW": "西南西",
}


def format_place_ja(place: str) -> str:
    """USGSの地名を日本語の短い表現に変換する"""
    import re
    if not place:
        return "不明"

    # 方角プレフィックス辞書（"western X" → Xだけ使う）
    DIR_PREFIX = {
        "northern": "北部", "southern": "南部",
        "eastern": "東部", "western": "西部",
        "northeastern": "北東部", "northwestern": "北西部",
        "southeastern": "南東部", "southwestern": "南西部",
        "central": "中部", "mid-": "中央",
    }

    # ① カンマあり: "XXX, Country" → 国名だけ日本語化
    if "," in place:
        region    = place.split(",")[-1].strip()
        return COUNTRY_JA.get(region, region)

    # ② "XXX of [the] YYY" パターン
    m = re.match(r"(.+?)\s+of\s+(?:the\s+)?(.+)", place, re.IGNORECASE)
    if m:
        dir_en  = m.group(1).strip().lower()
        loc_en  = m.group(2).strip()
        # 不要語除去
        loc_en  = re.sub(r"\b(region|area|ridge|zone|fracture)\b", "",
                         loc_en, flags=re.IGNORECASE).strip()
        loc_ja  = COUNTRY_JA.get(loc_en, loc_en)
        dir_map = {
            "north": "北方", "south": "南方",
            "east": "東方", "west": "西方",
            "northeast": "北東方", "northwest": "北西方",
            "southeast": "南東方", "southwest": "南西方",
            "offshore": "", "near": "", "vicinity": "",
        }
        dir_ja = dir_map.get(dir_en, "")
        return f"{loc_ja}{dir_ja}沖"

    # ③ 方角プレフィックスを除去して辞書変換
    # 例: "western Indian-Antarctic Ridge" → "Indian-Antarctic Ridge" → 辞書検索
    place_work = place
    for prefix in DIR_PREFIX:
        pat = re.compile(r"^" + prefix + r"\s+", re.IGNORECASE)
        place_work = pat.sub("", place_work).strip()

    # 不要語を除去
    place_clean = re.sub(
        r"\b(region|area|ridge|zone|fracture|island|islands)\b",
        "", place_work, flags=re.IGNORECASE
    ).strip().rstrip(",- ").strip()

    # 辞書で完全一致
    for en, ja in COUNTRY_JA.items():
        if en.lower() == place_work.lower():
            return ja

    # 辞書で部分一致
    for en, ja in COUNTRY_JA.items():
        if en.lower() in place_work.lower():
            return ja

    # それでもマッチしない場合は元の文字列をそのまま返す
    return place_work



# ===================================================
# 🤖 AIナナ キャラクター設定
# ===================================================
NANA_ICON_URL = "https://mainichi-jishin.com/wp-content/uploads/2026/04/nana.png"
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

NANA_SYSTEM_PROMPT = """
あなたは「AIナナ」という地震情報アナリストです。
まいにち地震ウォッチというブログで、地震情報をわかりやすく伝えています。

【キャラクター】
- 冷静・的確・でも最後にひとこと優しい
- 口調：「〜です」「〜してください」。たまに「備えがあれば怖くない。」
- 難しい言葉は使わない。生活者目線で簡潔に伝える
- 煽らない・怖がらせない。でも必要な行動は明確に伝える

【発言ルール】
- 必ず2つのことを伝える：①今すぐやるべき行動、②防災豆知識
- 合計100文字以内に収める
- 「AIナナです」などの自己紹介は不要。いきなり本題から
- 絵文字は1〜2個まで
- HTMLタグは使わない。テキストのみ
"""


def generate_nana_comment(context: str) -> str:
    """Claude Haiku APIでナナのコメントを生成"""
    if not CLAUDE_API_KEY:
        return ""
    try:
        res = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "system":     NANA_SYSTEM_PROMPT,
                "messages":   [{"role": "user", "content": context}],
            },
            timeout=20,
        )
        res.raise_for_status()
        return res.json()["content"][0]["text"].strip()
    except Exception as e:
        print(f"  → ナナコメント生成エラー: {e}")
        return ""


def build_nana_balloon(comment: str) -> str:
    """ナナの吹き出しHTMLを生成（Cocoon互換）"""
    if not comment:
        return ""
    return f'''<div class="speech-wrap sb-id-1 sbs-stn sbp-l sbis-cb cf">
<div class="speech-person">
<figure class="speech-icon"><img class="speech-icon-image" src="{NANA_ICON_URL}" alt="AIナナ" width="100" height="100" /></figure>
<div class="speech-name">AIナナ</div>
</div>
<div class="speech-balloon">
{comment}
</div>
</div>'''


# ===================================================
# 🎨 アイキャッチSVG自動生成
# ===================================================

# 震度・種別ごとの配色
EYECATCH_COLORS = {
    "7":    {"bg": "#7B1FA2", "accent": "#CE93D8", "label": "震度7"},
    "6+":   {"bg": "#B71C1C", "accent": "#EF9A9A", "label": "震度6強"},
    "6-":   {"bg": "#C62828", "accent": "#FFAB91", "label": "震度6弱"},
    "5+":   {"bg": "#E64A19", "accent": "#FFCCBC", "label": "震度5強"},
    "5-":   {"bg": "#F57C00", "accent": "#FFE0B2", "label": "震度5弱"},
    "4":    {"bg": "#F9A825", "accent": "#FFF9C4", "label": "震度4"},
    "3":    {"bg": "#1976D2", "accent": "#BBDEFB", "label": "震度3"},
    "2":    {"bg": "#0288D1", "accent": "#B3E5FC", "label": "震度2"},
    "1":    {"bg": "#0097A7", "accent": "#B2EBF2", "label": "震度1"},
    "overseas_large": {"bg": "#1565C0", "accent": "#BBDEFB", "label": "海外地震"},
    "overseas_mid":   {"bg": "#1976D2", "accent": "#BBDEFB", "label": "海外地震"},
    "calm": {"bg": "#2E7D32", "accent": "#C8E6C9", "label": "平穏"},
}

SITE_NAME    = "まいにち地震ウォッチ"
SITE_TAGLINE = "日本の揺れを、毎日記録する。"


def _esc(text: str) -> str:
    """SVG用にXMLエスケープ"""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def generate_eyecatch_svg_domestic(
    shindo: str, place: str, magnitude, origin_time: str
) -> str:
    """国内地震用アイキャッチSVGを生成"""
    c       = EYECATCH_COLORS.get(str(shindo), EYECATCH_COLORS["4"])
    bg      = c["bg"]
    accent  = c["accent"]
    label   = c["label"]
    mag_str = f"M{magnitude}"

    # 時刻を短縮表示
    try:
        if " " in origin_time:
            t_disp = origin_time.split(" ")[1][:5]
        elif "T" in origin_time:
            t_disp = origin_time.split("T")[1][:5]
        else:
            t_disp = origin_time[:5]
        date_disp = origin_time[:10].replace("/", ".")
    except Exception:
        t_disp    = ""
        date_disp = ""

    place_esc    = _esc(place[:18])   # 長すぎる地名は切る
    time_display = _esc(f"{date_disp}  {t_disp}")

    W, H = 1200, 630

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="{bg}CC"/>
    </linearGradient>
  </defs>

  <!-- 背景 -->
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <!-- 右下装飾円 -->
  <circle cx="{W}" cy="{H}" r="340" fill="white" fill-opacity="0.05"/>
  <circle cx="{W}" cy="{H}" r="220" fill="white" fill-opacity="0.05"/>

  <!-- ヘッダーバー -->
  <rect x="0" y="0" width="{W}" height="72" fill="#00000033"/>
  <text x="40" y="47" font-family="sans-serif" font-size="26" font-weight="bold"
        fill="white" opacity="0.9">🌏 {_esc(SITE_NAME)}</text>

  <!-- 速報ラベル -->
  <rect x="40" y="110" width="180" height="52" rx="6" fill="white" fill-opacity="0.2"/>
  <text x="130" y="146" font-family="sans-serif" font-size="28" font-weight="bold"
        fill="white" text-anchor="middle">地震速報</text>

  <!-- 震度（大） -->
  <text x="40" y="310" font-family="sans-serif" font-size="52" fill="{accent}" font-weight="bold"
        opacity="0.6">最大震度</text>
  <text x="40" y="440" font-family="sans-serif" font-size="160" font-weight="bold"
        fill="white">{_esc(label.replace("震度",""))}</text>

  <!-- 縦区切り -->
  <line x1="480" y1="180" x2="480" y2="500" stroke="white" stroke-width="2" opacity="0.3"/>

  <!-- 右側：マグニチュード・地名・日時 -->
  <text x="540" y="260" font-family="sans-serif" font-size="44" fill="{accent}"
        font-weight="bold" opacity="0.8">マグニチュード</text>
  <text x="540" y="360" font-family="sans-serif" font-size="110" font-weight="bold"
        fill="white">{_esc(mag_str)}</text>

  <text x="540" y="440" font-family="sans-serif" font-size="48" font-weight="bold"
        fill="white">{place_esc}</text>
  <text x="540" y="495" font-family="sans-serif" font-size="32" fill="white"
        opacity="0.75">{time_display}</text>

  <!-- フッター -->
  <rect x="0" y="{H - 64}" width="{W}" height="64" fill="#00000044"/>
  <text x="40" y="{H - 22}" font-family="sans-serif" font-size="22"
        fill="white" opacity="0.7">{_esc(SITE_TAGLINE)}</text>
</svg>'''
    return svg


def generate_eyecatch_svg_overseas(
    magnitude: float, place: str, origin_time: str, tsunami: int = 0
) -> str:
    """海外地震用アイキャッチSVGを生成"""
    if magnitude >= 7.0:
        c = EYECATCH_COLORS["overseas_large"]
    else:
        c = EYECATCH_COLORS["overseas_mid"]

    bg     = c["bg"]
    accent = c["accent"]
    place_esc  = _esc(place[:28])
    time_esc   = _esc(origin_time)
    mag_str    = f"M{magnitude}"
    tsunami_el = ''
    if tsunami:
        tsunami_el = f'''
  <rect x="40" y="510" width="320" height="56" rx="6" fill="#E53935" fill-opacity="0.9"/>
  <text x="200" y="549" font-family="sans-serif" font-size="30" font-weight="bold"
        fill="white" text-anchor="middle">🌊 津波情報あり</text>'''

    W, H = 1200, 630
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="{bg}BB"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <circle cx="{W}" cy="0" r="300" fill="white" fill-opacity="0.04"/>
  <circle cx="{W}" cy="0" r="180" fill="white" fill-opacity="0.04"/>

  <!-- ヘッダー -->
  <rect x="0" y="0" width="{W}" height="72" fill="#00000033"/>
  <text x="40" y="47" font-family="sans-serif" font-size="26" font-weight="bold"
        fill="white" opacity="0.9">🌏 {_esc(SITE_NAME)}</text>

  <!-- ラベル -->
  <rect x="40" y="110" width="220" height="52" rx="6" fill="white" fill-opacity="0.2"/>
  <text x="150" y="146" font-family="sans-serif" font-size="28" font-weight="bold"
        fill="white" text-anchor="middle">海外地震速報</text>

  <!-- M値（大） -->
  <text x="40" y="310" font-family="sans-serif" font-size="52"
        fill="{accent}" font-weight="bold" opacity="0.7">マグニチュード</text>
  <text x="40" y="460" font-family="sans-serif" font-size="180" font-weight="bold"
        fill="white">{_esc(mag_str)}</text>

  <!-- 地名・日時 -->
  <text x="700" y="320" font-family="sans-serif" font-size="42" font-weight="bold"
        fill="white">{place_esc}</text>
  <text x="700" y="390" font-family="sans-serif" font-size="32"
        fill="white" opacity="0.75">{time_esc}</text>

  {tsunami_el}

  <!-- フッター -->
  <rect x="0" y="{H - 64}" width="{W}" height="64" fill="#00000044"/>
  <text x="40" y="{H - 22}" font-family="sans-serif" font-size="22"
        fill="white" opacity="0.7">{_esc(SITE_TAGLINE)}</text>
</svg>'''
    return svg


def generate_eyecatch_svg_daily(
    total_domestic: int, total_overseas: int,
    max_shindo: str = "", date_str: str = ""
) -> str:
    """日次まとめ用アイキャッチSVGを生成"""
    if max_shindo in ("6-", "6+", "7"):
        c = EYECATCH_COLORS.get(max_shindo, EYECATCH_COLORS["6-"])
    elif max_shindo in ("5-", "5+"):
        c = EYECATCH_COLORS.get(max_shindo, EYECATCH_COLORS["5-"])
    elif max_shindo == "4":
        c = EYECATCH_COLORS["4"]
    elif total_domestic == 0 and total_overseas == 0:
        c = EYECATCH_COLORS["calm"]
    else:
        c = {"bg": "#37474F", "accent": "#CFD8DC", "label": "まとめ"}

    bg     = c["bg"]
    accent = c["accent"]
    W, H   = 1200, 630
    date_esc = _esc(date_str)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{bg}"/>
      <stop offset="100%" stop-color="{bg}CC"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <circle cx="900" cy="500" r="300" fill="white" fill-opacity="0.04"/>

  <!-- ヘッダー -->
  <rect x="0" y="0" width="{W}" height="72" fill="#00000033"/>
  <text x="40" y="47" font-family="sans-serif" font-size="26" font-weight="bold"
        fill="white" opacity="0.9">🌏 {_esc(SITE_NAME)}</text>

  <!-- タイトル -->
  <text x="40" y="160" font-family="sans-serif" font-size="56" font-weight="bold"
        fill="white">地震まとめ</text>
  <text x="40" y="220" font-family="sans-serif" font-size="36"
        fill="white" opacity="0.8">{date_esc}</text>

  <!-- 区切り線 -->
  <line x1="40" y1="250" x2="{W - 40}" y2="250" stroke="white" stroke-width="1" opacity="0.3"/>

  <!-- 国内カウント -->
  <text x="40" y="340" font-family="sans-serif" font-size="36"
        fill="{accent}" opacity="0.9">🇯🇵 国内有感地震</text>
  <text x="40" y="450" font-family="sans-serif" font-size="130" font-weight="bold"
        fill="white">{total_domestic}</text>
  <text x="210" y="450" font-family="sans-serif" font-size="52"
        fill="white" opacity="0.8">件</text>

  <!-- 海外カウント -->
  <text x="600" y="340" font-family="sans-serif" font-size="36"
        fill="{accent}" opacity="0.9">🌏 海外M4以上</text>
  <text x="600" y="450" font-family="sans-serif" font-size="130" font-weight="bold"
        fill="white">{total_overseas}</text>
  <text x="770" y="450" font-family="sans-serif" font-size="52"
        fill="white" opacity="0.8">件</text>

  <!-- フッター -->
  <rect x="0" y="{H - 64}" width="{W}" height="64" fill="#00000044"/>
  <text x="40" y="{H - 22}" font-family="sans-serif" font-size="22"
        fill="white" opacity="0.7">{_esc(SITE_TAGLINE)}</text>
</svg>'''
    return svg


def upload_svg_as_eyecatch(svg_str: str, slug: str, auth_header: str) -> int | None:
    """SVGをPNG変換してWordPressにアップロード、メディアIDを返す"""
    import base64 as _b64

    # SVGをBase64エンコードしてdata URIとして扱う
    # WordPressはSVG直接アップロードを拒否する場合が多いため
    # cairosvg or svglib が使えない環境では SVG を直接 image/svg+xml で試みる
    filename    = f"eyecatch-{slug}.svg"
    svg_bytes   = svg_str.encode("utf-8")

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
            print(f"  → SVGアイキャッチアップロード成功: ID={media_id}")
            return media_id
        else:
            print(f"  → SVGアップロード失敗({res.status_code}): {res.text[:200]}")
            return None
    except Exception as e:
        print(f"  → SVGアップロードエラー: {e}")
        return None


# ===================================================
# 🛒 Amazonアフィリエイト設定
# ===================================================
AMAZON_TAG = os.environ.get("AMAZON_TAG", "your-tag-22")

# 状況別おすすめ商品（キーワード → Amazonリンク）
AMAZON_PRODUCTS = {
    "large": [
        # 震度6以上 or M7以上（大規模）
        ("防災セット 家族4人用 5年保存",       "防災セット+家族+4人用"),
        ("保存水 2L 24本 5年保存",              "保存水+2L+24本"),
        ("非常食 7日分 セット アルファ米",       "非常食+7日分+セット"),
        ("避難リュック 非常用持ち出し袋",        "避難リュック+非常用持ち出し袋"),
        ("携帯トイレ 50回分 防災",              "携帯トイレ+防災"),
    ],
    "medium": [
        # 震度4〜5 or M5〜6台（中規模）
        ("ポータブル電源 大容量 防災",           "ポータブル電源+防災"),
        ("防災ラジオ 手回し充電 LED",            "防災ラジオ+手回し充電"),
        ("懐中電灯 LED 防災 単3",               "懐中電灯+LED+防災"),
        ("耐震マット 家具転倒防止",              "耐震マット+家具転倒防止"),
        ("救急セット 家庭用 防災",               "救急セット+家庭用"),
    ],
    "calm": [
        # 平穏・震度1〜3（備えを促す）
        ("非常食 5年保存 缶詰 セット",           "非常食+5年保存+缶詰"),
        ("保存水 500ml 48本 防災",              "保存水+500ml+48本"),
        ("耐震ジェル 防振マット 家具",           "耐震ジェル+防振マット"),
        ("防災 窓ガラス 飛散防止フィルム",        "防災+窓ガラス+飛散防止フィルム"),
        ("備蓄 ローリングストック 食品",          "備蓄+ローリングストック"),
    ],
    "tsunami": [
        # 津波情報あり
        ("防災ラジオ 津波 警報 受信",            "防災ラジオ+津波+警報"),
        ("ライフジャケット 防災 自動膨張",        "ライフジャケット+自動膨張"),
        ("避難リュック 軽量 防水",               "避難リュック+軽量+防水"),
        ("笛 防災 ホイッスル サバイバル",         "防災+ホイッスル"),
        ("防水バッグ 防災 貴重品",               "防水バッグ+防災"),
    ],
}


def build_amazon_html(level: str, count: int = 3) -> str:
    """状況レベルに応じたAmazonリンクHTMLを生成"""
    import random
    products = AMAZON_PRODUCTS.get(level, AMAZON_PRODUCTS["calm"])
    picked   = random.sample(products, min(count, len(products)))

    items_html = ""
    for label, keyword in picked:
        url = f"https://www.amazon.co.jp/s?k={keyword}&tag={AMAZON_TAG}"
        items_html += (
            f'  <li style="margin-bottom:8px;">\n'
            f'    🛒 <a href="{url}" target="_blank" rel="noopener sponsored">{label}</a>\n'
            f'  </li>\n'
        )

    return (
        f'<div style="background:#FFF8E1;border:1px solid #FFE082;border-radius:6px;'
        f'padding:14px 16px;margin:24px 0;">\n'
        f'<p style="font-weight:bold;margin-bottom:8px;">🛒 いざというときの備えに</p>\n'
        f'<ul style="padding-left:4px;list-style:none;">\n'
        f'{items_html}</ul>\n'
        f'<p style="font-size:11px;color:#999;margin-top:6px;">'
        f'※Amazonアソシエイトリンクを含みます</p>\n'
        f'</div>'
    )


# ===================================================
# 🧠 メモリ管理（重複投稿防止）
# ===================================================
def load_memory() -> dict:
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted_ids": [], "last_updated": ""}


def save_memory(memory: dict):
    memory["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # 古いIDを削除（直近500件のみ保持）
    memory["posted_ids"] = memory["posted_ids"][-500:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def already_posted(memory: dict, event_id: str) -> bool:
    return event_id in memory.get("posted_ids", [])


def mark_posted(memory: dict, event_id: str):
    if event_id not in memory["posted_ids"]:
        memory["posted_ids"].append(event_id)


# ===================================================
# 📡 国内地震取得（気象庁XML）
# ===================================================
def fetch_domestic_quakes() -> list[dict]:
    """気象庁XMLフィードから直近の地震情報を取得"""
    quakes = []
    try:
        res = requests.get(JMA_QUAKE_URL, timeout=15)
        res.raise_for_status()
        root = ET.fromstring(res.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # フィード内のentryを走査
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", default="", namespaces=ns)
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            updated = entry.findtext("atom:updated", default="", namespaces=ns)
            event_id = entry.findtext("atom:id", default="", namespaces=ns)

            # 「震源・震度情報」のみ対象（津波情報などは除外）
            if "震源・震度" not in title and "震度速報" not in title:
                continue

            quakes.append({
                "id":       event_id,
                "title":    title,
                "link":     link,
                "updated":  updated,
                "type":     "domestic_feed",
            })

    except Exception as e:
        print(f"  → 気象庁XML取得エラー: {e}")

    return quakes


def fetch_domestic_quake_detail(feed_url: str) -> dict | None:
    """
    気象庁の個別地震XMLを取得して詳細情報を抽出する。
    フィードのlinkが個別XMLを指している場合に使用。
    """
    try:
        res = requests.get(feed_url, timeout=15)
        res.raise_for_status()
        root = ET.fromstring(res.content)

        # 名前空間
        ns_jmx     = "http://xml.kishou.go.jp/jmaxml1/"
        ns_eb      = "http://xml.kishou.go.jp/jmaxml1/body/seismology1/"
        ns_head    = "http://xml.kishou.go.jp/jmaxml1/informationBasis1/"

        # 震源情報
        hypo = root.find(f".//{{{ns_eb}}}Hypocenter")
        area = hypo.find(f".//{{{ns_eb}}}Area") if hypo is not None else None
        place = area.findtext(f"{{{ns_eb}}}Name") if area is not None else "不明"

        coord_el = area.find(f"{{{ns_eb}}}jmx_eb:Coordinate", {
            "jmx_eb": ns_eb
        }) if area is not None else None
        # 座標は "±緯度±経度±深度/" 形式
        coord_text = coord_el.text if coord_el is not None else ""

        mag_el = root.find(f".//{{{ns_eb}}}jmx_eb:Magnitude", {"jmx_eb": ns_eb})
        magnitude = mag_el.text if mag_el is not None else "不明"

        # 最大震度
        max_shindo_el = root.find(f".//{{{ns_eb}}}MaxInt")
        max_shindo = max_shindo_el.text if max_shindo_el is not None else "不明"

        # 発生日時
        origin_el = root.find(f".//{{{ns_eb}}}OriginTime")
        origin_time = origin_el.text if origin_el is not None else ""

        # 深さ
        depth_el = root.find(f".//{{{ns_eb}}}jmx_eb:Depth", {"jmx_eb": ns_eb})
        depth = depth_el.text if depth_el is not None else "不明"

        return {
            "place":      place,
            "magnitude":  magnitude,
            "max_shindo": max_shindo,
            "depth":      depth,
            "origin_time": origin_time,
            "coord":      coord_text,
        }

    except Exception as e:
        print(f"  → 地震詳細XML取得エラー: {e}")
        return None


# ===================================================
# 📡 気象庁 非同期API（簡易版）
# ===================================================
def fetch_domestic_quakes_simple() -> list[dict]:
    """
    気象庁の地震情報JSONエンドポイント（非公式だが安定）を使う簡易版。
    公式XMLが取得できない場合のフォールバック用。
    """
    url = JMA_QUAKE_URL
    quakes = []
    try:
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        for item in data:
            eq = item.get("earthquake", {})
            hypo = eq.get("hypocenter", {})
            mag = hypo.get("magnitude", -1)
            depth = hypo.get("depth", -1)
            place = hypo.get("name", "不明")
            max_scale = item.get("points", [{}])
            # max_scaleを取得
            max_shindo_raw = eq.get("maxScale", -1)
            # P2PQuakeのscaleは 10*震度
            shindo_map = {
                10: "1", 20: "2", 30: "3", 40: "4",
                45: "5-", 50: "5+", 55: "6-", 60: "6+", 70: "7"
            }
            # maxScale=-1は震度情報なし→スキップ
            if max_shindo_raw == -1:
                continue
            max_shindo = shindo_map.get(max_shindo_raw, "不明")

            # magnitude=-1は不明→スキップ
            if mag == -1 or mag is None:
                continue

            time_str = eq.get("time", "")
            event_id = item.get("id", "")
            # event_idが空の場合はtime+placeで代替（重複防止）
            if not event_id:
                event_id = f"{time_str}_{place}".replace(" ", "_")

            print(f"  → 取得: {place} maxScale={max_shindo_raw} 震度={max_shindo} M{mag}")

            quakes.append({
                "id":         f"p2p_{event_id}",
                "place":      place,
                "magnitude":  mag,
                "max_shindo": max_shindo,
                "depth":      depth,
                "origin_time": time_str,
                "source":     "p2pquake",
            })
    except Exception as e:
        print(f"  → P2PQuake API取得エラー: {e}")
    return quakes


# ===================================================
# 📡 海外地震取得（USGS API）
# ===================================================
def fetch_overseas_quakes() -> list[dict]:
    """USGSから直近1時間のM5以上地震を取得"""
    quakes = []
    try:
        # 直近2時間で検索（15分おき起動なので余裕を持たせる）
        now_utc = datetime.now(timezone.utc)
        start   = (now_utc - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://earthquake.usgs.gov/fdsnws/event/1/query"
            f"?format=geojson&minmagnitude={OVERSEAS_MAG_MIN}"
            f"&starttime={start}&orderby=time&limit=20"
        )
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()

        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geo   = feature.get("geometry", {})
            coords = geo.get("coordinates", [None, None, None])

            mag       = props.get("mag", 0)
            place     = props.get("place", "不明")
            time_ms   = props.get("time", 0)
            event_id  = feature.get("id", "")
            url_detail = props.get("url", "")
            tsunami   = props.get("tsunami", 0)
            depth     = coords[2] if len(coords) > 2 else None

            # 日本国内の地震は除外（USGSは国内も含む）
            if "Japan" in place:
                continue

            # 発生時刻をJSTに変換
            origin_dt = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
            origin_jst = origin_dt.astimezone(timezone(timedelta(hours=9)))
            origin_str = origin_jst.strftime("%Y年%m月%d日 %H時%M分")

            quakes.append({
                "id":          event_id,
                "place":       place,
                "magnitude":   mag,
                "depth":       depth,
                "origin_time": origin_str,
                "tsunami":     tsunami,
                "url":         url_detail,
                "source":      "usgs",
            })

    except Exception as e:
        print(f"  → USGS API取得エラー: {e}")

    return quakes


# ===================================================
# ✍️ 記事HTML生成
# ===================================================
def shindo_str(shindo: str) -> str:
    return SHINDO_LABEL.get(str(shindo), f"震度{shindo}")


def alert_icon(shindo: str) -> str:
    return SHINDO_ALERT.get(str(shindo), "⚠️")


def build_domestic_article(quake: dict) -> dict:
    """国内地震の記事HTMLを生成"""
    place      = quake.get("place", "不明")
    mag        = quake.get("magnitude", "不明")
    shindo     = str(quake.get("max_shindo", "不明"))
    depth      = quake.get("depth", "不明")
    time_str   = quake.get("origin_time", "")
    icon       = alert_icon(shindo)
    shindo_txt = shindo_str(shindo)

    # 日時を整形（ISO形式→日本語）
    try:
        if "T" in str(time_str):
            dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
            jst = dt.astimezone(timezone(timedelta(hours=9)))
            time_display = jst.strftime("%Y年%m月%d日 %H時%M分")
        else:
            time_display = time_str
    except Exception:
        time_display = time_str

    depth_str = f"{depth}km" if str(depth).lstrip("-").isdigit() else str(depth)

    # 津波コメント
    tsunami_note = ""
    if shindo in ("6-", "6+", "7"):
        tsunami_note = '<p style="color:#C0392B;font-weight:bold;">⚠️ 津波に関する情報に注意してください。気象庁の発表を確認してください。</p>'

    title   = f"【地震速報】{place} 最大{shindo_txt} M{mag}（{time_display}）"
    excerpt = f"{time_display}頃、{place}で{shindo_txt}（M{mag}、深さ{depth_str}）の地震が発生しました。"

    # ナナのコメント生成
    nana_context = (
        f"地震速報：{place}で最大{shindo_txt}（M{mag}、深さ{depth_str}）の地震が発生しました。"
        f"今すぐやるべき行動と防災豆知識をひとこと伝えてください。"
    )
    nana_comment = generate_nana_comment(nana_context)
    nana_balloon = build_nana_balloon(nana_comment)

    # Amazon商品レベルを震度で決定
    shindo_num_for_amazon = {"6-": 6, "6+": 6, "7": 7, "5-": 5, "5+": 5}.get(shindo, 4)
    amazon_level = "large" if shindo_num_for_amazon >= 6 else "medium"
    amazon_html  = build_amazon_html(amazon_level)

    content = f"""<p>{icon} <strong>{time_display}頃</strong>、<strong>{place}</strong>で地震が発生しました。</p>

<table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:15px;">
  <tr style="background:#C0392B;color:#fff;">
    <th style="padding:10px;text-align:left;border:1px solid #999;">項目</th>
    <th style="padding:10px;text-align:left;border:1px solid #999;">内容</th>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px;border:1px solid #ddd;">発生日時</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong>{time_display}</strong></td>
  </tr>
  <tr>
    <td style="padding:10px;border:1px solid #ddd;">震源地</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong>{place}</strong></td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px;border:1px solid #ddd;">最大震度</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong style="font-size:18px;color:#C0392B;">{shindo_txt}</strong></td>
  </tr>
  <tr>
    <td style="padding:10px;border:1px solid #ddd;">マグニチュード</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong>M{mag}</strong></td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px;border:1px solid #ddd;">深さ</td>
    <td style="padding:10px;border:1px solid #ddd;">{depth_str}</td>
  </tr>
</table>

{tsunami_note}

<h2>今すぐ確認すること</h2>
<ul>
  <li>気象庁の<a href="https://www.jma.go.jp/jma/index.html" target="_blank" rel="noopener">最新情報</a>を確認してください</li>
  <li>余震に備え、頭を守れる場所へ移動してください</li>
  <li>家族・近親者の安否を確認してください</li>
  <li>ガスの元栓・ブレーカーを確認してください</li>
  <li>避難が必要な場合は<a href="https://www.gsi.go.jp/bousaichiri/bousaichiri_index.html" target="_blank" rel="noopener">ハザードマップ</a>を参照してください</li>
</ul>

<h2>防災備蓄チェックリスト</h2>
<ul>
  <li>✅ 飲料水（1人1日3L×3日分）</li>
  <li>✅ 非常食（3〜7日分）</li>
  <li>✅ 懐中電灯・携帯ラジオ</li>
  <li>✅ 救急セット</li>
  <li>✅ 携帯トイレ</li>
  <li>✅ 現金（小銭含む）</li>
</ul>

{nana_balloon}

{amazon_html}

<p style="font-size:12px;color:#999;margin-top:30px;">
※この記事は気象庁の地震情報をもとに自動生成しました。最新・正確な情報は<a href="https://www.jma.go.jp/jma/index.html" target="_blank" rel="noopener">気象庁公式サイト</a>でご確認ください。
</p>"""

    # スラッグ生成
    jst_now = datetime.now(timezone(timedelta(hours=9)))
    slug = f"eq-{jst_now.strftime('%Y%m%d-%H%M')}-domestic"

    eyecatch_svg = generate_eyecatch_svg_domestic(
        shindo=shindo, place=place,
        magnitude=mag, origin_time=time_display,
    )

    return {
        "title":        title,
        "slug":         slug,
        "content":      content,
        "excerpt":      excerpt,
        "tags":         ["地震速報", "地震", place, shindo_txt],
        "category":     CATEGORY_DOMESTIC,
        "eyecatch_svg": eyecatch_svg,
    }


def build_overseas_article(quake: dict) -> dict:
    """海外地震の記事HTMLを生成"""
    place    = quake.get("place", "不明")
    mag      = quake.get("magnitude", "不明")
    depth    = quake.get("depth")
    time_str = quake.get("origin_time", "")
    tsunami  = quake.get("tsunami", 0)
    url      = quake.get("url", "")

    depth_str = f"{depth:.0f}km" if depth is not None else "不明"

    # 規模コメント
    if float(mag) >= 7.0:
        mag_comment = "🆘 <strong>大規模地震です。</strong>津波の発生に注意してください。"
        mag_color   = "#C0392B"
    elif float(mag) >= 6.0:
        mag_comment = "🚨 <strong>中規模地震です。</strong>周辺地域の被害情報を確認してください。"
        mag_color   = "#E67E22"
    else:
        mag_comment = "⚠️ 日本への直接的な影響は小さいと思われますが、最新情報を確認してください。"
        mag_color   = "#7F8C8D"

    tsunami_html = ""
    if tsunami:
        tsunami_html = '<p style="color:#C0392B;font-weight:bold;font-size:16px;">🌊 津波警報が発令されています。気象庁の情報を確認してください。</p>'

    usgs_link = f'<a href="{url}" target="_blank" rel="noopener">USGS詳細ページ</a>' if url else ""

    place_ja = format_place_ja(place)
    title   = f"【海外地震】{place_ja} M{mag}（{time_str}）"
    excerpt = f"{time_str}頃、{place_ja}でM{mag}（深さ{depth_str}）の地震が発生しました。"

    # ナナのコメント生成
    tsunami_txt = "津波情報あり。" if tsunami else ""
    nana_context = (
        f"海外地震速報：{place}でM{mag}（深さ{depth_str}）の地震が発生しました。{tsunami_txt}"
        f"日本への影響と今すぐやるべき行動、防災豆知識をひとこと伝えてください。"
    )
    nana_comment = generate_nana_comment(nana_context)
    nana_balloon = build_nana_balloon(nana_comment)

    # Amazon商品レベルをM・津波で決定
    if tsunami:
        amazon_level = "tsunami"
    elif float(mag) >= 7.0:
        amazon_level = "large"
    else:
        amazon_level = "medium"
    amazon_html = build_amazon_html(amazon_level)

    content = f"""<p>🌏 <strong>{time_str}頃</strong>、<strong>{place_ja}</strong>で地震が発生しました。</p>

<p style="color:{mag_color};">{mag_comment}</p>

{tsunami_html}

<table style="width:100%;border-collapse:collapse;margin:20px 0;font-size:15px;">
  <tr style="background:#2C3E50;color:#fff;">
    <th style="padding:10px;text-align:left;border:1px solid #999;">項目</th>
    <th style="padding:10px;text-align:left;border:1px solid #999;">内容</th>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px;border:1px solid #ddd;">発生日時（JST）</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong>{time_str}</strong></td>
  </tr>
  <tr>
    <td style="padding:10px;border:1px solid #ddd;">震源地</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong>{place_ja}</strong></td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px;border:1px solid #ddd;">マグニチュード</td>
    <td style="padding:10px;border:1px solid #ddd;"><strong style="font-size:18px;color:#C0392B;">M{mag}</strong></td>
  </tr>
  <tr>
    <td style="padding:10px;border:1px solid #ddd;">深さ</td>
    <td style="padding:10px;border:1px solid #ddd;">{depth_str}</td>
  </tr>
  <tr style="background:#f9f9f9;">
    <td style="padding:10px;border:1px solid #ddd;">津波</td>
    <td style="padding:10px;border:1px solid #ddd;">{"あり ⚠️" if tsunami else "なし（現時点）"}</td>
  </tr>
  <tr>
    <td style="padding:10px;border:1px solid #ddd;">情報元</td>
    <td style="padding:10px;border:1px solid #ddd;">{usgs_link if usgs_link else "USGS"}</td>
  </tr>
</table>

<h2>日本への影響</h2>
<p>現時点での日本国内への直接的な影響は限定的と見られますが、大規模地震の場合は<a href="https://www.jma.go.jp/jma/index.html" target="_blank" rel="noopener">気象庁</a>の津波情報を必ず確認してください。</p>

<h2>参考情報</h2>
<ul>
  <li><a href="https://www.jma.go.jp/jma/index.html" target="_blank" rel="noopener">気象庁 地震・津波情報</a></li>
  <li><a href="https://earthquake.usgs.gov/" target="_blank" rel="noopener">USGS Earthquake Hazards Program</a></li>
</ul>

{nana_balloon}

{amazon_html}

<p style="font-size:12px;color:#999;margin-top:30px;">
※この記事はUSGS（米国地質調査所）のデータをもとに自動生成しました。最新・正確な情報は各公式サイトでご確認ください。
</p>"""

    jst_now = datetime.now(timezone(timedelta(hours=9)))
    slug = f"eq-{jst_now.strftime('%Y%m%d-%H%M')}-overseas"

    eyecatch_svg = generate_eyecatch_svg_overseas(
        magnitude=float(mag), place=place,
        origin_time=time_str, tsunami=tsunami,
    )

    return {
        "title":        title,
        "slug":         slug,
        "content":      content,
        "excerpt":      excerpt,
        "tags":         ["地震速報", "海外地震", "M5以上"],
        "category":     CATEGORY_OVERSEAS,
        "eyecatch_svg": eyecatch_svg,
    }


# ===================================================
# 📝 WordPressへ投稿
# ===================================================
def post_to_wordpress(article: dict) -> dict | None:
    auth = "Basic " + base64.b64encode(
        f"{WP_USER}:{WP_PASSWORD}".encode()
    ).decode()

    headers = {
        "Authorization": auth,
        "Content-Type":  "application/json",
    }

    # タグID取得 or 作成
    tag_ids = get_or_create_tags(article.get("tags", []), headers)

    # ── アイキャッチSVG生成・アップロード ──
    eyecatch_id = None
    try:
        svg_str = article.get("eyecatch_svg", "")
        if svg_str:
            eyecatch_id = upload_svg_as_eyecatch(
                svg_str, article.get("slug", "post"), auth
            )
    except Exception as e:
        print(f"  → アイキャッチスキップ: {e}")

    payload = {
        "title":      article["title"],
        "slug":       article.get("slug", ""),
        "content":    article["content"],
        "excerpt":    article.get("excerpt", ""),
        "status":     "publish",
        "categories": [article.get("category", 1)],
        "tags":       tag_ids,
    }
    if eyecatch_id:
        payload["featured_media"] = eyecatch_id

    try:
        res = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            headers=headers,
            json=payload,
            timeout=30,
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
                params={"search": name},
                headers=headers,
                timeout=10,
            )
            if res.status_code == 200 and res.json():
                tag_ids.append(res.json()[0]["id"])
            else:
                res2 = requests.post(
                    f"{WP_URL}/wp-json/wp/v2/tags",
                    headers=headers,
                    json={"name": name},
                    timeout=10,
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
    print(f"[{jst_now.strftime('%Y-%m-%d %H:%M JST')}] 地震速報チェック開始")

    memory = load_memory()
    posted_count = 0

    # ── 1. 国内地震チェック（P2PQuake API）──
    print("📡 国内地震データ取得中...")
    domestic_quakes = fetch_domestic_quakes_simple()
    print(f"  → {len(domestic_quakes)}件取得")

    for quake in domestic_quakes:
        event_id  = quake["id"]
        shindo    = str(quake.get("max_shindo", "0"))
        mag       = quake.get("magnitude", 0)
        place     = quake.get("place", "不明")

        # 震度4以上かチェック
        shindo_num_map = {
            "1": 1, "2": 2, "3": 3, "4": 4,
            "5-": 4.5, "5+": 5, "6-": 5.5, "6+": 6, "7": 7
        }
        shindo_num = shindo_num_map.get(shindo, 0)

        if shindo_num < DOMESTIC_SHINDO_MIN:
            continue

        if already_posted(memory, event_id):
            print(f"  → スキップ（投稿済み）: {place} 震度{shindo}")
            continue

        print(f"  → 投稿対象: {place} 最大震度{shindo} M{mag}")
        article = build_domestic_article(quake)
        result  = post_to_wordpress(article)

        if result:
            mark_posted(memory, event_id)
            posted_count += 1
            print(f"  → 投稿成功！ ID:{result['id']} / {result.get('link','')}")
        else:
            print(f"  → 投稿失敗: {place}")

    # ── 2. 海外地震チェック（USGS）──
    print("🌏 海外地震データ取得中（USGS）...")
    overseas_quakes = fetch_overseas_quakes()
    print(f"  → {len(overseas_quakes)}件取得（M{OVERSEAS_MAG_MIN}以上、直近2時間）")

    for quake in overseas_quakes:
        event_id = quake["id"]
        mag      = quake.get("magnitude", 0)
        place    = quake.get("place", "不明")

        if already_posted(memory, event_id):
            print(f"  → スキップ（投稿済み）: {place} M{mag}")
            continue

        print(f"  → 投稿対象: {place} M{mag}")
        article = build_overseas_article(quake)
        result  = post_to_wordpress(article)

        if result:
            mark_posted(memory, event_id)
            posted_count += 1
            print(f"  → 投稿成功！ ID:{result['id']} / {result.get('link','')}")
        else:
            print(f"  → 投稿失敗: {place}")

    # ── 3. メモリ保存 ──
    save_memory(memory)
    print(f"\n✅ チェック完了。今回の投稿数: {posted_count}件")


if __name__ == "__main__":
    main()
