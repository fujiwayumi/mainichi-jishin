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
WP_URL      = os.environ.get("EQ_WP_URL", "https://your-earthquake-site.com")
WP_USER     = os.environ.get("EQ_WP_USER", "")
WP_PASSWORD = os.environ.get("EQ_WP_PASSWORD", "")

# 閾値
DOMESTIC_SHINDO_MIN = 4      # 国内：震度4以上
OVERSEAS_MAG_MIN    = 5.0    # 海外：M5.0以上

# カテゴリID（WordPressで事前に作成しておく）
CATEGORY_DOMESTIC = 1   # 国内地震
CATEGORY_OVERSEAS = 2   # 海外地震

# メモリファイル
MEMORY_FILE = "earthquake_memory.json"

# 気象庁 地震情報XML
JMA_QUAKE_URL = "https://www.data.jma.go.jp/developer/xml/feed/eqvol.xml"

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
# 🛒 Amazonアフィリエイト設定
# ===================================================
AMAZON_TAG = os.environ.get("AMAZON_TAG", "your-tag-22")

# 状況別おすすめ商品（キーワード → Amazonリンク）
AMAZON_PRODUCTS = {
    "large": [
        # 震度6以上 or M7以上（大規模）
        ("防災セット 家族4人用 5年保存",       "bousai-set+family+4nin"),
        ("保存水 2L 24本 5年保存",              "hozonmizu+2L+24hon"),
        ("非常食 7日分 セット アルファ米",       "hijyoshoku+7days+set"),
        ("避難リュック 非常用持ち出し袋",        "hinan+rucksack+hijyo"),
        ("携帯トイレ 50回分 防災",              "keitai+toilet+bousai"),
    ],
    "medium": [
        # 震度4〜5 or M5〜6台（中規模）
        ("ポータブル電源 大容量 防災",           "portable+dengen+bousai"),
        ("防災ラジオ 手回し充電 LED",            "bousai+radio+temawashi"),
        ("懐中電灯 LED 防災 単3",               "kaichu+dento+LED+bousai"),
        ("耐震マット 家具転倒防止",              "taishin+mat+kagu"),
        ("救急セット 家庭用 防災",               "kyukyu+set+katei"),
    ],
    "calm": [
        # 平穏・震度1〜3（備えを促す）
        ("非常食 5年保存 缶詰 セット",           "hijyoshoku+5nen+kanme"),
        ("保存水 500ml 48本 防災",              "hozonmizu+500ml+48hon"),
        ("耐震ジェル 防振マット 家具",           "taishin+gel+bousai"),
        ("防災 窓ガラス 飛散防止フィルム",        "bousai+garasu+film"),
        ("備蓄 ローリングストック 食品",          "bichiku+rolling+stock"),
    ],
    "tsunami": [
        # 津波情報あり
        ("防災ラジオ 津波 警報 受信",            "bousai+radio+tsunami"),
        ("ライフジャケット 防災 自動膨張",        "life+jacket+jidou"),
        ("避難リュック 軽量 防水",               "hinan+rucksack+kerryo"),
        ("笛 防災 ホイッスル サバイバル",         "fue+bousai+whistle"),
        ("防水バッグ 防災 貴重品",               "boosui+bag+bousai"),
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
    url = "https://www.p2pquake.net/api/v2/history?codes=551&limit=10"
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
            max_shindo = shindo_map.get(max_shindo_raw, str(max_shindo_raw))
            time_str = eq.get("time", "")
            event_id = item.get("id", "")

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

{amazon_html}

<p style="font-size:12px;color:#999;margin-top:30px;">
※この記事は気象庁の地震情報をもとに自動生成しました。最新・正確な情報は<a href="https://www.jma.go.jp/jma/index.html" target="_blank" rel="noopener">気象庁公式サイト</a>でご確認ください。
</p>"""

    # スラッグ生成
    jst_now = datetime.now(timezone(timedelta(hours=9)))
    slug = f"eq-{jst_now.strftime('%Y%m%d-%H%M')}-domestic"

    return {
        "title":    title,
        "slug":     slug,
        "content":  content,
        "excerpt":  excerpt,
        "tags":     ["地震速報", "地震", place, shindo_txt],
        "category": CATEGORY_DOMESTIC,
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

    title   = f"【海外地震】{place} M{mag}（{time_str}）"
    excerpt = f"{time_str}頃、{place}でM{mag}（深さ{depth_str}）の地震が発生しました。"

    # Amazon商品レベルをM・津波で決定
    if tsunami:
        amazon_level = "tsunami"
    elif float(mag) >= 7.0:
        amazon_level = "large"
    else:
        amazon_level = "medium"
    amazon_html = build_amazon_html(amazon_level)

    content = f"""<p>🌏 <strong>{time_str}頃</strong>、<strong>{place}</strong>で地震が発生しました。</p>

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
    <td style="padding:10px;border:1px solid #ddd;"><strong>{place}</strong></td>
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

{amazon_html}

<p style="font-size:12px;color:#999;margin-top:30px;">
※この記事はUSGS（米国地質調査所）のデータをもとに自動生成しました。最新・正確な情報は各公式サイトでご確認ください。
</p>"""

    jst_now = datetime.now(timezone(timedelta(hours=9)))
    slug = f"eq-{jst_now.strftime('%Y%m%d-%H%M')}-overseas"

    return {
        "title":    title,
        "slug":     slug,
        "content":  content,
        "excerpt":  excerpt,
        "tags":     ["地震速報", "海外地震", "M5以上"],
        "category": CATEGORY_OVERSEAS,
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

    payload = {
        "title":      article["title"],
        "slug":       article.get("slug", ""),
        "content":    article["content"],
        "excerpt":    article.get("excerpt", ""),
        "status":     "publish",
        "categories": [article.get("category", 1)],
        "tags":       tag_ids,
    }

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
