#!/usr/bin/env python3
"""
【まいにち地震ウォッチ 過去記事の楽天リンク追加スクリプト】
- 地震速報記事：「🛒 いざというときの備えに」ボックスを2ボタン形式に書き換える
- コンテンツ記事：本文中のAmazonリンクの横に「／楽天市場で見る」を追加する
- Amazonリンクのタグも mainichi-jishin-22 にそろえる
- 何度実行しても安全（書き換え済みの記事はスキップ）
- DRY_RUN=true のときは記事を変更せず、対象件数だけ表示する
"""

import os
import re
import base64
import urllib.parse
import requests

# ===================================================
# ⚙️ 設定
# ===================================================
WP_URL      = os.environ.get("EQ_WP_URL", "https://mainichi-jishin.com").rstrip("/")
WP_USER     = os.environ.get("EQ_WP_USER", "")
WP_PASSWORD = os.environ.get("EQ_WP_PASSWORD", "")
DRY_RUN     = os.environ.get("DRY_RUN", "true").lower() == "true"

AMAZON_TAG     = "mainichi-jishin-22"
RAKUTEN_AFF_ID = "588d647a.e52acd92.588d647b.47962ed1"

AUTH = "Basic " + base64.b64encode(f"{WP_USER}:{WP_PASSWORD}".encode()).decode()
HEADERS = {"Authorization": AUTH, "Content-Type": "application/json"}

BTN = (
    "display:inline-block;padding:3px 10px;margin:4px 6px 0 0;border-radius:4px;"
    "font-size:13px;font-weight:bold;color:#fff;text-decoration:none;"
)


# ===================================================
# 🔗 リンク生成（earthquake_alert.py と同じ形式）
# ===================================================
def rakuten_aff_url(target_url: str) -> str:
    enc = urllib.parse.quote(target_url, safe="")
    return f"https://hb.afl.rakuten.co.jp/hgc/{RAKUTEN_AFF_ID}/?pc={enc}&m={enc}"


def rakuten_search_url(keyword: str) -> str:
    # 楽天は「+」や%20だと検索窓に「+」が残るため全角スペースでつなぐ
    kw = keyword.replace("+", "　").replace(" ", "　")
    return rakuten_aff_url(
        f"https://search.rakuten.co.jp/search/mall/{urllib.parse.quote(kw)}/"
    )


def build_item(label: str, keyword_raw: str) -> str:
    # 保存済みURLのキーワードはエンコード済みのこともあるので一度デコード（+は残す）
    keyword = urllib.parse.unquote(keyword_raw)
    amazon_kw  = urllib.parse.quote(keyword, safe="+")
    amazon_url = f"https://www.amazon.co.jp/s?k={amazon_kw}&tag={AMAZON_TAG}"
    return (
        f'<li style="margin-bottom:12px;">\n'
        f'    🛒 {label}<br>\n'
        f'    <a href="{amazon_url}" target="_blank" rel="noopener sponsored" '
        f'style="{BTN}background:#FF9900;">Amazonで見る</a>\n'
        f'    <a href="{rakuten_search_url(keyword)}" target="_blank" rel="noopener sponsored" '
        f'style="{BTN}background:#BF0000;">楽天市場で見る</a>\n'
        f'  </li>'
    )


# 旧形式の1商品分：<li ...> 🛒 <a href="Amazon検索URL" ...>ラベル</a> </li>
OLD_ITEM_RE = re.compile(
    r'<li[^>]*>\s*🛒\s*'
    r'<a href="https://www\.amazon\.co\.jp/s\?k=([^&"]+)&(?:amp;|#038;)?tag=[^"]*"[^>]*>'
    r'([^<]+)</a>\s*</li>',
    re.DOTALL,
)

OLD_NOTE = "※Amazonアソシエイトリンクを含みます"
NEW_NOTE = "※Amazonアソシエイト・楽天アフィリエイトのリンクを含みます"


# 本文中のAmazon検索リンク（直後に楽天リンクがまだ無いもの）
# ※earthquake_content.py の記事（AIが本文に書いたリンク）用
INLINE_AMAZON_RE = re.compile(
    r'<a href="https://www\.amazon\.co\.jp/s\?k=([^&"]+)&(?:amp;|#038;)?tag=[^"]*"([^>]*)>((?:(?!</a>).)*)</a>'
    r'(?!\s*(?:<span[^>]*>)?\s*[／/]?\s*<a[^>]*hb\.afl\.rakuten)',
    re.DOTALL,
)


def _inline_repl(m):
    keyword    = urllib.parse.unquote(m.group(1))
    amazon_kw  = urllib.parse.quote(keyword, safe="+")
    amazon     = (f'<a href="https://www.amazon.co.jp/s?k={amazon_kw}&tag={AMAZON_TAG}"'
                  f'{m.group(2)}>{m.group(3)}</a>')
    rakuten    = (f'<span style="margin-left:4px;">／<a href="{rakuten_search_url(keyword)}" '
                  f'target="_blank" rel="noopener sponsored">楽天市場で見る</a></span>')
    return amazon + rakuten


def convert(content: str) -> tuple[str, int]:
    # ① 地震速報記事の「備えに」ボックス → 2ボタン形式
    new, n1 = OLD_ITEM_RE.subn(lambda m: build_item(m.group(2).strip(), m.group(1)), content)
    if n1:
        new = new.replace(OLD_NOTE, NEW_NOTE)
    # ② コンテンツ記事の本文中リンク → 横に楽天リンクを追加
    new, n2 = INLINE_AMAZON_RE.subn(_inline_repl, new)
    return new, n1 + n2


# ===================================================
# 📥 全記事取得
# ===================================================
def fetch_all_posts():
    page = 1
    while True:
        res = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            headers=HEADERS,
            params={
                "per_page": 100, "page": page, "context": "edit",
                "status": "publish", "_fields": "id,title,content",
            },
            timeout=30,
        )
        if res.status_code == 400:
            break
        res.raise_for_status()
        posts = res.json()
        if not posts:
            break
        yield from posts
        total_pages = int(res.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            break
        page += 1


# ===================================================
# 🚀 メイン
# ===================================================
def main():
    print(f"対象サイト: {WP_URL}")
    print(f"モード: {'🔍 お試し（変更しない）' if DRY_RUN else '✏️ 本番（書き換える）'}\n")

    checked = changed = items = failed = 0
    unmatched = []

    for post in fetch_all_posts():
        checked += 1
        pid     = post["id"]
        title   = post["title"].get("raw") or post["title"].get("rendered", "")
        content = post["content"].get("raw", "")

        new_content, n = convert(content)

        if n == 0:
            # Amazonリンクはあるのに旧形式に当てはまらない記事（別スクリプトの記事など）
            if "amazon.co.jp/" in content and "hb.afl.rakuten.co.jp" not in content:
                unmatched.append(f"{pid}: {title}")
            continue

        print(f"  → ID {pid}: {n}件  {title}")
        changed += 1
        items   += n

        if DRY_RUN:
            continue

        res = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{pid}",
            headers=HEADERS,
            json={"content": new_content},
            timeout=30,
        )
        if res.status_code not in (200, 201):
            failed += 1
            print(f"    ❌ 更新失敗({res.status_code}): {res.text[:150]}")

    print(f"\nチェックした記事: {checked}件")
    print(f"書き換え{'対象' if DRY_RUN else '済み'}: {changed}記事 / {items}商品")
    if failed:
        print(f"更新失敗: {failed}件")
    if unmatched:
        print(f"\n⚠️ Amazonリンクはあるが形式が違うため未対応: {len(unmatched)}件")
        for u in unmatched[:30]:
            print(f"  - {u}")
    if DRY_RUN:
        print("\n問題なければ dry_run を false にして再実行してください。")


if __name__ == "__main__":
    main()
