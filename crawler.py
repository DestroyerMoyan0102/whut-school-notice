# -*- coding: utf-8 -*-
"""
crawler.py —— 负责两件事：
  ① 访问学校网站，把通知列表「抓下来」
  ② 从抓到的网页里，把通知的【标题 / 链接 / 发布时间】「解析出来」

关于武汉理工大学 i.whut.edu.cn 的实际情况（已实测确认，不是猜的）：
  - 网站只有 HTTP 能通，HTTPS(443) 不通，所以必须用 http:// 开头
  - 不需要登录，没有反爬，服务器是 nginx
  - 网页编码是 UTF-8
  - 每条通知在网页里的样子是这样的：

        <ul class="list_t">
          <li>
            <span class="list_tag">【<a href="./znbm/jwc/">本科生院</a>】</span>
            <a href="./znbm/jwc/202609/t20260929_1420007.shtml"
               target="_blank"
               title="【本科生院】关于……的通知"
               class="list_text">【本科生院】关于……</a>
            <span class="date hidden-xs">2026-09-29</span>
          </li>
          ...

    所以我们的解析规则是：
      1) 先找出 <ul class="list_t"> 里的每一个 <li>
      2) 在 <li> 里找 class="list_text" 的那个 <a>，取它的 href 和 title
         （优先用 title，因为页面上显示的文字会被截断成 "……"）
      3) 取 <li> 里 <span class="date hidden-xs"> 里的日期

【关于「发布时间」的重要说明】
  实测发现：武汉理工大学综合信息网的通知，**只有日期，没有具体时分**。
  - 列表页显示的是：2026-09-29
  - 点进详情页看到的也是：发布时间：2026-09-29
  全站都找不到 "2026-09-29 14:32" 这种精确到分钟的时间。

  所以本程序采取的处理方式是（date 级比较）：
      由 main.py 算出 cutoff_date（时间窗口起点的「日期」）
      只要 通知日期 >= cutoff_date 就保留

  举例：第一次运行是在 2026-09-29 20:00
        往前 24 小时 = 2026-09-28 20:00，它的日期 = 2026-09-28
        于是 09-28 和 09-29 发布的通知都会保留。

  这样做的理由是「宁可多报，不可漏报」：
  网页没给时间，我们无法知道 09-28 那条是上午发的还是晚上发的，
  如果按「09-28 00:00」和「09-28 20:00」去比较，就会漏掉 09-28 傍晚的通知。

  多报出来的那部分，由 state.py 的「已发送链接清单」负责去重，
  所以最终不会重复发同一封通知。
"""

import html as html_lib
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from urllib.parse import urljoin

import config


class CrawlError(Exception):
    """所有栏目都抓取失败时抛出的异常。"""


# ==========================================================
# 正则表达式：用来从 HTML 文本里把需要的信息「抠」出来
# ==========================================================
# 匹配一个完整的 <li> ... </li>
_LI_RE = re.compile(r"<li>(.*?)</li>", re.S)

# 匹配一个完整的 <a ...>文字</a>，第一组是标签里的属性，第二组是链接文字
_A_TAG_RE = re.compile(r"<a\s([^>]*)>(.*?)</a>", re.S)

# 匹配 <span class="date hidden-xs">2026-09-29</span>，取出日期文字
_DATE_SPAN_RE = re.compile(r'<span[^>]*class="date[^"]*"[^>]*>(.*?)</span>', re.S)

# 从链接里兜底取日期，例如 t20260929_1420007.shtml -> 2026 / 09 / 29
_URL_DATE_RE = re.compile(r"t(\d{4})(\d{2})(\d{2})_\d+\.shtml")


def _get_attr(attrs_text, attr_name):
    """从 `href="xxx" title="yyy"` 这样的属性字符串里，取出某个属性的值。"""
    matched = re.search(r'\b' + attr_name + r'\s*=\s*"([^"]*)"', attrs_text)
    return matched.group(1) if matched else None


# ==========================================================
# 第一步：抓网页
# ==========================================================
def fetch_html(url):
    """
    访问一个网址，返回网页的 HTML 文本（字符串）。
    失败会抛出异常，交给调用方处理。
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": config.USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=config.REQUEST_TIMEOUT) as response:
        raw_bytes = response.read()

    # 学校网站是 UTF-8。这里先按 UTF-8 解码，
    # 万一以后改成 GBK 也不会直接崩掉，会自动换一种编码再试。
    for encoding in ("utf-8", "gbk"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


# ==========================================================
# 第二步：解析「发布时间」
# ==========================================================
def parse_date(date_text):
    """
    把网页上的日期文字转成 Python 的 date 对象。
    认得出 2026-09-29 / 2026/09/29 / 2026年09月29日 这几种写法。
    认不出来就返回 None。
    """
    if not date_text:
        return None

    text = date_text.strip().replace("年", "-").replace("月", "-").replace("日", "")
    text = text.replace("/", "-").replace(".", "-")
    # 只保留前面 10 个字符（2026-09-29），
    # 防止后面跟着 "浏览量：123" 之类的多余内容
    text = text[:10]

    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def date_from_url(url):
    """
    兜底方案：如果页面上实在找不到日期，就从链接里推。
    链接形如 .../202609/t20260929_1420007.shtml，其中 20260929 就是发布日期。
    """
    matched = _URL_DATE_RE.search(url)
    if not matched:
        return None
    year, month, day = (int(x) for x in matched.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


# ==========================================================
# 第三步：解析「通知列表页」
# ==========================================================
def parse_list_page(html_text, page_url, section_name):
    """
    输入：一个列表页的 HTML
    输出：这个页面上所有通知组成的列表，每条是
          {"title": 标题, "url": 原文链接, "date": 发布日期(date对象),
           "date_text": 网页上原本显示的日期文字, "section": 来源栏目}
    """
    notices = []

    for li_html in _LI_RE.findall(html_text):
        # 找出这个 <li> 里带 class="list_text" 的那个 <a> 标签
        target_attrs = None
        target_inner_text = None
        for attrs_text, inner_text in _A_TAG_RE.findall(li_html):
            if "list_text" in attrs_text:
                target_attrs = attrs_text
                target_inner_text = inner_text
                break

        # 没有 list_text 的 <li>（比如左侧导航菜单）直接跳过
        if target_attrs is None:
            continue

        href = _get_attr(target_attrs, "href")
        if not href or href.startswith("javascript"):
            continue

        # 标题优先用 title 属性，因为页面上显示的文字被截断过
        title = _get_attr(target_attrs, "title") or target_inner_text or ""
        # 把 &quot; 之类的 HTML 转义字符还原成真正的引号
        title = html_lib.unescape(title).strip()
        title = re.sub(r"\s+", " ", title)

        if not title:
            continue

        # 详情页链接：列表页里是相对路径，用 urljoin 拼成完整网址
        full_url = urljoin(page_url, href)

        # 发布时间：先看页面上的 <span class="date hidden-xs">
        date_text = None
        matched_date = _DATE_SPAN_RE.search(li_html)
        if matched_date:
            date_text = html_lib.unescape(matched_date.group(1)).strip()

        published = parse_date(date_text)

        # 页面上解析不出来就用链接里的日期兜底
        if published is None:
            published = date_from_url(full_url)
            if published is not None:
                date_text = published.strftime("%Y-%m-%d")

        if published is None:
            # 两条路都失败：打印提示并跳过，绝不静默忽略
            print("[WARN] 无法解析发布时间，已跳过：%s（%s）" % (title, full_url))
            continue

        notices.append(
            {
                "title": title,
                "url": full_url,
                "date": published,
                "date_text": date_text,
                "section": section_name,
            }
        )

    return notices


# ==========================================================
# 第四步：翻页抓取所有栏目
# ==========================================================
def build_page_url(section_url, page_index):
    """拼出某一页的网址。page_index 从 0 开始：0 -> index.shtml，1 -> index_1.shtml"""
    if page_index == 0:
        file_name = config.PAGE_URL_FIRST
    else:
        file_name = config.PAGE_URL_TEMPLATE.format(page=page_index)
    return urljoin(section_url, file_name)


def crawl_all_sections(cutoff_date):
    """
    把所有栏目、所有需要的页都抓一遍。

    cutoff_date 是本次要看的最早日期（由 main.py 根据状态算出来）。
    抓到「这一页最老的日期已经早于 cutoff_date」就停止翻页，
    保证不会漏掉窗口内出现的任何通知。
    """
    all_notices = []
    success_sections = 0

    for section in config.SECTIONS:
        section_name = section["name"]
        section_url = section["url"]
        section_ok = False

        for page_index in range(config.MAX_PAGES_PER_SECTION):
            page_url = build_page_url(section_url, page_index)
            print("[INFO] 正在抓取「%s」第 %d 页：%s" % (section_name, page_index + 1, page_url))

            try:
                html_text = fetch_html(page_url)
            except Exception as error:
                # 第 1 页就打不开 = 这个栏目整体访问失败；后面几页失败 = 抓到头了
                if page_index == 0:
                    print("[ERROR] 无法访问：%s（%s）" % (page_url, error))
                else:
                    print("[WARN] 该页访问失败，已停止本栏目翻页：%s（%s）" % (page_url, error))
                break

            section_ok = True
            page_notices = parse_list_page(html_text, page_url, section_name)

            if not page_notices:
                print("[WARN] 这一页没有解析到任何通知，可能是网站页面结构变了：%s" % page_url)
                break

            all_notices.extend(page_notices)

            oldest_date = min(item["date"] for item in page_notices)
            print(
                "[INFO] 第 %d 页解析到 %d 条，本页最早日期 %s"
                % (page_index + 1, len(page_notices), oldest_date)
            )

            # 这一页最老的日期都已经比时间窗口更早了，后面几页只会更老，不用再翻
            if oldest_date < cutoff_date:
                break

            time.sleep(config.REQUEST_DELAY)

        if section_ok:
            success_sections += 1

    if success_sections == 0:
        raise CrawlError("所有通知栏目都访问失败")

    # 去重：不同栏目理论上不会重复，但保险起见按链接去一次重
    unique_notices = {}
    for item in all_notices:
        unique_notices[item["url"]] = item

    return list(unique_notices.values())


# ==========================================================
# 第五步：时间筛选
# ==========================================================
def filter_by_time(notices, cutoff_date):
    """
    只保留「日期 >= cutoff_date」的通知。

    cutoff_date 由 main.py 结合补跑状态算出来，含义是「时间窗口起点的日期」。
    因为网站只提供日期、没有时分，所以这里按「日期」而不是精确时间比较
    （详细说明见本文件开头的注释）。

    返回筛选后的通知列表。
    """
    return [item for item in notices if item["date"] >= cutoff_date]


# ==========================================================
# 第六步：关键词筛选
# ==========================================================
def filter_by_keywords(notices, keywords):
    """
    只保留「标题里包含任意一个关键词」的通知。
    第一版只看标题，不搜索正文。
    """
    if not keywords:
        return list(notices)

    kept = []
    for item in notices:
        for keyword in keywords:
            if keyword in item["title"]:
                kept.append(item)
                break
    return kept
