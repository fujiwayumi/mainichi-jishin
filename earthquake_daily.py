#!/usr/bin/env python3
"""
【地震日次まとめ 自動投稿システム】
- その日（JST）に発生した震度1以上の国内地震 + M4以上の海外地震をまとめて1記事投稿
- 地震ゼロの日も「平穏な1日」として防災・地震関連ニュースを添えて投稿
- 毎日1回（深夜）実行
"""

import os
import json
import requests
import base64
import email.utils
import feedparser
from datetime import datetime, timezone, timedelta

# ===================================================
# ⚙️ 設定
# ===================================================
WP_URL      = os.environ.get("EQ_WP_URL", "https://your-earthquake-site.com")
WP_USER     = os.environ.get("EQ_WP_USER", "")
WP_PASSWORD = os.environ.get("EQ_WP_PASSWORD", "")

CATEGORY_DAILY = 3  # 日次まとめカテゴリ

SHINDO_LABEL = {
    "1": "震度1", "2": "震度2", "3": "震度3",
    "4": "震度4",
    "5-": "震度5弱", "5+": "震度5強",
    "6-": "震度6弱", "6+": "震度6強",
    "7": "震度7",
}
# ===================================================
# 🛒 Amazonアフィリエイト設定
# ===================================================
AMAZON_TAG = os.environ.get("AMAZON_TAG", "your-tag-22")

AMAZON_PRODUCTS = {
    "large": [
        ("防災セット 家族4人用 5年保存",       "bousai-set+family+4nin"),
        ("保存水 2L 24本 5年保存",              "hozonmizu+2L+24hon"),
        ("非常食 7日分 セット アルファ米",       "hijyoshoku+7days+set"),
        ("避難リュック 非常用持ち出し袋",        "hinan+rucksack+hijyo"),
        ("携帯トイレ 50回分 防災",              "keitai+toilet+bousai"),
    ],
    "medium": [
        ("ポータブル電源 大容量 防災",           "portable+dengen+bousai"),
        ("防災ラジオ 手回し充電 LED",            "bousai+radio+temawashi"),
        ("懐中電灯 LED 防災 単3",               "kaichu+dento+LED+bousai"),
        ("耐震マット 家具転倒防止",              "taishin+mat+kagu"),
        ("救急セット 家庭用 防災",               "kyukyu+set+katei"),
    ],
    "calm": [
        ("非常食 5年保存 缶詰 セット",           "hijyoshoku+5nen+kanme"),
        ("保存水 500ml 48本 防災",              "hozonmizu+500ml+48hon"),
        ("耐震ジェル 防振マット 家具",           "taishin+gel+bousai"),
        ("防災 窓ガラス 飛散防止フィルム",        "bousai+garasu+film"),
        ("備蓄 ローリングストック 食品",          "bichiku+rolling+stock"),
    ],
    "tsunami": [
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


# 防災・地震関連ニュースのRSSフィード
NEWS_RSS_FEEDS = [
    {"url": "https://www3.nhk.or.jp/rss/news/cat1.xml",          "label": "NHK 社会"},
    {"url": "https://www3.nhk.or.jp/rss/news/cat3.xml",          "label": "NHK 科学・医療"},
    {"url": "https://www.jma.go.jp/bosai/info/rss/regular.xml",  "label": "気象庁 防災情報"},
    {"url": "https://news.google.com/rss/search?q=when:24h+地震+防災+津波+震災+災害&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "防災ニュース"},
    {"url": "https://news.google.com/rss/search?q=when:24h+南海トラフ+首都直下+震災+復興&hl=ja&gl=JP&ceid=JP:ja",
                                                                  "label": "震災・復興ニュース"},
    {"url": "https://news.google.com/rss/search?q=when:24h+(earthquake+OR+tsunami+OR+seismic)&ceid=US:en&hl=en-US&gl=US",
                                                                  "label": "Earthquake News"},
]

# ニュースフィルタ用キーワード
NEWS_KEYWORDS = [
    "地震", "震度", "津波", "震災", "防災", "災害", "避難", "備蓄",
    "南海トラフ", "首都直下", "活断層", "液状化", "土砂", "噴火",
    "earthquake", "tsunami", "seismic", "disaster", "fault",
]


# ===================================================
# 📡 防災・地震関連ニュース取得（RSS）
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


def fetch_disaster_news(hours: int = 24) -> list[dict]:
    """防災・地震関連ニュースをRSSから取得してキーワードフィルタ"""
    cutoff   = datetime.now(timezone.utc) - timedelta(hours=hours)
    all_news = []

    for feed_info in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries[:30]:
                pub = parse_rss_date(entry)
                if pub < cutoff:
                    continue
                title   = entry.get("title", "")
                summary = entry.get("summary", "")[:200]
                link    = entry.get("link", "")
                text    = title + " " + summary

                # キーワードフィルタ
                if not any(kw in text for kw in NEWS_KEYWORDS):
                    continue

                all_news.append({
                    "title":     title,
                    "summary":   summary,
                    "link":      link,
                    "published": pub.astimezone(timezone(timedelta(hours=9))).strftime("%H:%M"),
                    "source":    feed_info["label"],
                })
        except Exception as e:
            print(f"  → RSS取得エラー ({feed_info['label']}): {e}")

    # 重複タイトルを除去して最大10件
    seen, unique = set(), []
    for item in all_news:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)
    return unique[:10]


# ===================================================
# 📡 当日の国内地震取得（P2PQuake）
# ===================================================
def fetch_today_domestic() -> list[dict]:
    """当日JST分の国内地震を取得"""
    jst_now   = datetime.now(timezone(timedelta(hours=9)))
    today_str = jst_now.strftime("%Y/%m/%d")
    quakes    = []

    try:
        res = requests.get(
            "https://www.p2pquake.net/api/v2/history",
            params={"codes": 551, "limit": 100},
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()

        shindo_map = {
            10: "1", 20: "2", 30: "3", 40: "4",
            45: "5-", 50: "5+", 55: "6-", 60: "6+", 70: "7"
        }

        for item in data:
            eq    = item.get("earthquake", {})
            hypo  = eq.get("hypocenter", {})
            time_str = eq.get("time", "")

            if not time_str.startswith(today_str):
                continue

            max_scale = eq.get("maxScale", -1)
            max_shindo = shindo_map.get(max_scale, "不明")

            quakes.append({
                "id":         item.get("id", ""),
                "place":      hypo.get("name", "不明"),
                "magnitude":  hypo.get("magnitude", -1),
                "max_shindo": max_shindo,
                "depth":      hypo.get("depth", -1),
                "origin_time": time_str,
            })
    except Exception as e:
        print(f"  → 国内地震取得エラー: {e}")

    return quakes


# ===================================================
# 📡 当日の海外地震取得（USGS）
# ===================================================
def fetch_today_overseas() -> list[dict]:
    """当日JSTのM4以上海外地震を取得"""
    jst_now   = datetime.now(timezone(timedelta(hours=9)))
    jst_start = jst_now.replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = jst_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    quakes    = []

    try:
        res = requests.get(
            "https://earthquake.usgs.gov/fdsnws/event/1/query",
            params={
                "format":         "geojson",
                "minmagnitude":   4.0,
                "starttime":      utc_start,
                "orderby":        "magnitude",
                "limit":          50,
            },
            timeout=15,
        )
        res.raise_for_status()
        data = res.json()

        for feature in data.get("features", []):
            props  = feature.get("properties", {})
            geo    = feature.get("geometry", {})
            coords = geo.get("coordinates", [None, None, None])
            place  = props.get("place", "不明")

            if "Japan" in place:
                continue

            mag      = props.get("mag", 0)
            time_ms  = props.get("time", 0)
            tsunami  = props.get("tsunami", 0)
            event_id = feature.get("id", "")
            depth    = coords[2] if len(coords) > 2 else None

            origin_dt  = datetime.fromtimestamp(time_ms / 1000, tz=timezone.utc)
            origin_jst = origin_dt.astimezone(timezone(timedelta(hours=9)))
            origin_str = origin_jst.strftime("%H:%M")

            quakes.append({
                "id":          event_id,
                "place":       place,
                "magnitude":   mag,
                "depth":       depth,
                "origin_time": origin_str,
                "tsunami":     tsunami,
            })
    except Exception as e:
        print(f"  → 海外地震取得エラー: {e}")

    return quakes


# ===================================================
# ✍️ 日次まとめ記事生成
# ===================================================
def build_daily_article(
    domestic: list[dict],
    overseas: list[dict],
    news: list[dict],
) -> dict:
    jst_now   = datetime.now(timezone(timedelta(hours=9)))
    date_str  = jst_now.strftime("%Y年%m月%d日")
    date_slug = jst_now.strftime("%Y%m%d")

    # ── 国内：震度順にソート ──
    shindo_order = {"7": 9, "6+": 8, "6-": 7, "5+": 6, "5-": 5,
                    "4": 4, "3": 3, "2": 2, "1": 1, "不明": 0}
    domestic_sorted = sorted(
        domestic,
        key=lambda q: shindo_order.get(str(q.get("max_shindo", "0")), 0),
        reverse=True,
    )
    max_quake   = domestic_sorted[0] if domestic_sorted else None
    total_count = len(domestic)

    # ── 国内テーブル or 平穏メッセージ ──
    if domestic_sorted:
        domestic_rows = ""
        for q in domestic_sorted[:20]:
            shindo_txt = SHINDO_LABEL.get(str(q.get("max_shindo", "")), f"震度{q.get('max_shindo','')}")
            mag   = q.get("magnitude", "-")
            place = q.get("place", "不明")
            t     = q.get("origin_time", "")
            try:
                t_disp = t.split(" ")[1][:5] if " " in t else t[:5]
            except Exception:
                t_disp = t
            domestic_rows += (
                f'  <tr>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;">{t_disp}</td>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;">{place}</td>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">{shindo_txt}</td>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;">M{mag}</td>\n'
                f'  </tr>\n'
            )
        domestic_html = (
            f'<h2>🇯🇵 国内の地震（{date_str}）</h2>\n'
            f'<p>本日の有感地震は <strong>{total_count}件</strong> 発生しました。</p>\n'
            f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:20px;">\n'
            f'  <tr style="background:#C0392B;color:#fff;">\n'
            f'    <th style="padding:8px;border:1px solid #999;">発生時刻</th>\n'
            f'    <th style="padding:8px;border:1px solid #999;">震源地</th>\n'
            f'    <th style="padding:8px;border:1px solid #999;">最大震度</th>\n'
            f'    <th style="padding:8px;border:1px solid #999;">M</th>\n'
            f'  </tr>\n'
            f'{domestic_rows}</table>'
        )
    else:
        domestic_html = (
            f'<h2>🇯🇵 国内の地震（{date_str}）</h2>\n'
            f'<div style="background:#E8F5E9;border-left:4px solid #4CAF50;padding:12px 16px;'
            f'margin:16px 0;border-radius:4px;">\n'
            f'✅ <strong>本日は有感地震がなく、平穏な1日でした。</strong>\n'
            f'日本では珍しいことですが、備えを怠らないようにしましょう。\n'
            f'</div>'
        )

    # ── 海外テーブル ──
    overseas_m5 = [q for q in overseas if q.get("magnitude", 0) >= 5.0]
    if overseas:
        overseas_sorted = sorted(overseas, key=lambda q: q.get("magnitude", 0), reverse=True)
        overseas_rows = ""
        for q in overseas_sorted[:15]:
            mag   = q.get("magnitude", "-")
            place = q.get("place", "不明")
            t     = q.get("origin_time", "")
            depth = q.get("depth")
            depth_str    = f"{depth:.0f}km" if depth is not None else "-"
            tsunami_mark = " 🌊" if q.get("tsunami") else ""
            overseas_rows += (
                f'  <tr>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;">{t}</td>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;">{place}{tsunami_mark}</td>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;font-weight:bold;">M{mag}</td>\n'
                f'    <td style="padding:8px;border:1px solid #ddd;">{depth_str}</td>\n'
                f'  </tr>\n'
            )
        overseas_html = (
            f'<h2>🌏 海外の地震（{date_str}）</h2>\n'
            f'<p>本日のM4以上の海外地震は <strong>{len(overseas)}件</strong>'
            f'（うちM5以上：{len(overseas_m5)}件）です。</p>\n'
            f'<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:20px;">\n'
            f'  <tr style="background:#2C3E50;color:#fff;">\n'
            f'    <th style="padding:8px;border:1px solid #999;">発生時刻(JST)</th>\n'
            f'    <th style="padding:8px;border:1px solid #999;">震源地</th>\n'
            f'    <th style="padding:8px;border:1px solid #999;">規模</th>\n'
            f'    <th style="padding:8px;border:1px solid #999;">深さ</th>\n'
            f'  </tr>\n'
            f'{overseas_rows}</table>\n'
            f'<p style="font-size:12px;color:#999;">🌊 = 津波情報あり　出典: USGS</p>'
        )
    else:
        overseas_html = (
            f'<h2>🌏 海外の地震（{date_str}）</h2>'
            f'<p>本日のM4以上の海外地震は観測されませんでした。</p>'
        )

    # ── 最大地震の強調バナー ──
    highlight = ""
    if max_quake:
        shindo_txt = SHINDO_LABEL.get(str(max_quake.get("max_shindo", "")), "不明")
        highlight = (
            f'<div style="background:#FFF3CD;border-left:4px solid #FFC107;'
            f'padding:12px 16px;margin:20px 0;border-radius:4px;">\n'
            f'⚠️ <strong>本日最大：{max_quake.get("place","不明")} '
            f'最大{shindo_txt} M{max_quake.get("magnitude","-")}</strong>\n'
            f'</div>'
        )

    # ── 防災ニュースセクション ──
    if news:
        news_items = ""
        for item in news:
            title_txt = item["title"]
            link      = item["link"]
            source    = item["source"]
            summary   = item.get("summary", "")
            # summaryからHTMLタグを簡易除去
            import re
            summary_clean = re.sub(r"<[^>]+>", "", summary).strip()[:80]
            if summary_clean:
                summary_clean = f'<br><span style="font-size:12px;color:#666;">{summary_clean}…</span>'
            news_items += (
                f'  <li style="margin-bottom:10px;">\n'
                f'    <a href="{link}" target="_blank" rel="noopener">{title_txt}</a>'
                f'{summary_clean}\n'
                f'    <span style="font-size:11px;color:#999;margin-left:6px;">（{source}）</span>\n'
                f'  </li>\n'
            )
        news_html = (
            f'<h2>📰 本日の防災・地震関連ニュース</h2>\n'
            f'<ul style="line-height:1.9;">\n{news_items}</ul>'
        )
    else:
        news_html = ""

    # ── Amazonリンクのレベルを決定 ──
    shindo_order = {"7": 9, "6+": 8, "6-": 7, "5+": 6, "5-": 5, "4": 4, "3": 3, "2": 2, "1": 1}
    has_tsunami  = any(q.get("tsunami") for q in overseas)
    max_shindo_num = shindo_order.get(str(max_quake.get("max_shindo", "0")), 0) if max_quake else 0
    max_overseas_mag = max((q.get("magnitude", 0) for q in overseas), default=0)

    if has_tsunami:
        amazon_level = "tsunami"
    elif max_shindo_num >= 6 or max_overseas_mag >= 7.0:
        amazon_level = "large"
    elif max_shindo_num >= 4 or max_overseas_mag >= 5.0:
        amazon_level = "medium"
    else:
        amazon_level = "calm"
    amazon_html_block = build_amazon_html(amazon_level)

    # ── リード文（地震ゼロの日は平穏メッセージ）──
    if total_count == 0 and not overseas:
        lead = (
            f'<p>🗓️ <strong>{date_str}</strong> の地震活動まとめです。</p>\n'
            f'<p>本日は国内外ともに注目すべき地震活動はありませんでした。'
            f'平穏な1日でしたが、いつ大地震が起きてもおかしくない日本。'
            f'備えだけは毎日続けましょう。</p>'
        )
    else:
        lead = f'<p>🗓️ <strong>{date_str}</strong> の地震活動まとめです。</p>'

    # ── 記事本文を組み立て ──
    content = (
        f'{lead}\n\n'
        f'{highlight}\n\n'
        f'{domestic_html}\n\n'
        f'{overseas_html}\n\n'
        f'{news_html}\n\n'
        f'{amazon_html_block}\n\n'
        f'<h2>防災リンク</h2>\n'
        f'<ul>\n'
        f'  <li><a href="https://www.jma.go.jp/jma/index.html" target="_blank" rel="noopener">気象庁 地震・津波情報</a></li>\n'
        f'  <li><a href="https://earthquake.usgs.gov/" target="_blank" rel="noopener">USGS Earthquake Hazards</a></li>\n'
        f'  <li><a href="https://www.nhk.or.jp/kishou-saigai/earthquake/" target="_blank" rel="noopener">NHK 地震情報</a></li>\n'
        f'</ul>\n\n'
        f'<p style="font-size:12px;color:#999;margin-top:30px;">\n'
        f'※この記事はP2PQuake・USGS・各種RSSをもとに自動生成しました。'
        f'正確な情報は各公式サイトをご確認ください。\n'
        f'</p>'
    )

    # ── タイトル（地震ゼロは「平穏」を前面に）──
    if total_count == 0 and not overseas:
        title = f"【地震まとめ】{date_str} 本日は平穏な1日でした"
    else:
        title = f"【地震まとめ】{date_str} 国内{total_count}件・海外{len(overseas)}件"

    excerpt = f"{date_str}の地震活動まとめ。国内有感地震{total_count}件、海外M4以上{len(overseas)}件。"

    return {
        "title":    title,
        "slug":     f"eq-daily-{date_slug}",
        "content":  content,
        "excerpt":  excerpt,
        "tags":     ["地震まとめ", "地震", date_str],
        "category": CATEGORY_DAILY,
    }


# ===================================================
# 📝 WordPress投稿
# ===================================================
def post_to_wordpress(article: dict) -> dict | None:
    auth = "Basic " + base64.b64encode(
        f"{WP_USER}:{WP_PASSWORD}".encode()
    ).decode()
    headers = {
        "Authorization": auth,
        "Content-Type":  "application/json",
    }
    tag_ids = get_or_create_tags(article.get("tags", []), headers)
    payload = {
        "title":      article["title"],
        "slug":       article["slug"],
        "content":    article["content"],
        "excerpt":    article["excerpt"],
        "status":     "publish",
        "categories": [article.get("category", 1)],
        "tags":       tag_ids,
    }
    try:
        res = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts",
            headers=headers, json=payload, timeout=30,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"  → 投稿エラー: {e}")
        return None


def get_or_create_tags(tag_names, headers):
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
# 🚀 メイン
# ===================================================
def main():
    jst_now = datetime.now(timezone(timedelta(hours=9)))
    print(f"[{jst_now.strftime('%Y-%m-%d %H:%M JST')}] 地震日次まとめ開始")

    print("📡 国内地震データ取得中...")
    domestic = fetch_today_domestic()
    print(f"  → {len(domestic)}件")

    print("🌏 海外地震データ取得中...")
    overseas = fetch_today_overseas()
    print(f"  → {len(overseas)}件（M4以上）")

    print("📰 防災・地震関連ニュース取得中...")
    news = fetch_disaster_news(hours=24)
    print(f"  → {len(news)}件")

    print("✍️  記事生成中...")
    article = build_daily_article(domestic, overseas, news)
    print(f"  → タイトル: {article['title']}")

    print("📝 WordPress投稿中...")
    result = post_to_wordpress(article)
    if result:
        print(f"  → 投稿成功！ ID:{result['id']} / {result.get('link','')}")
    else:
        print("  → 投稿失敗")


if __name__ == "__main__":
    main()
