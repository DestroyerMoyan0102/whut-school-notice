# -*- coding: utf-8 -*-
"""
main.py —— 程序入口，把整个流程串起来。

运行方式（在 school_notice 文件夹里打开终端）：
    python main.py

完整流程：
    开始
     ↓
    读取状态（上次跑到哪儿了 → 决定这次要看多长时间的通知）
     ↓
    抓取：访问学校网站，把通知列表下载下来
     ↓
    时间筛选：只留时间窗口内发布的
     ↓
    关键词筛选：只留标题里含关键词的
     ↓
    去重：去掉以前已经发过的，只留真正的新通知
     ↓
    排序：本科生院 → 信息学院 → 留学交换 → 其他（按拼音首字母）
     ↓
    生成邮件正文
     ↓
    通过 QQ 邮箱发送
     ↓
    更新状态文件（记录这次跑到哪儿了）
     ↓
    结束

关于补跑：
    程序会记住上次成功运行的时间。如果电脑关机或断网错过了 12:00，
    下次开机运行时窗口会自动从「上次成功运行的时间」开始，
    把中间漏掉的通知一起补上（最多往前追溯 config.MAX_CATCHUP_DAYS 天）。
"""

import sys
import traceback
from datetime import datetime

import config
import crawler
import email_sender
import organizer
import state


def _make_stdout_never_crash():
    """
    Windows 终端遇到个别特殊字符时可能报编码错，
    这里让它遇到不认识的字符用 ? 代替，而不是直接让程序崩掉。
    """
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def main():
    _make_stdout_never_crash()

    run_time = datetime.now()

    print("=" * 60)
    print("武汉理工大学校园通知 · 抓取与邮件提醒")
    print("运行时间：%s" % run_time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    # ------------------------------------------------------
    # 第一步：读取状态，算出这次的时间窗口
    # ------------------------------------------------------
    saved_state = state.load_state()
    window_start, is_catchup, _clamped = state.compute_window_start(saved_state, run_time)
    cutoff_date = window_start.date()

    print(
        "[INFO] 时间窗口：%s ～ %s（按日期比较，起点日期 %s）"
        % (
            window_start.strftime("%Y-%m-%d %H:%M"),
            run_time.strftime("%Y-%m-%d %H:%M"),
            cutoff_date.strftime("%Y-%m-%d"),
        )
    )

    # ------------------------------------------------------
    # 第二步：抓取通知列表
    # ------------------------------------------------------
    print("[INFO] 开始访问学校官网...")
    try:
        all_notices = crawler.crawl_all_sections(cutoff_date)
    except crawler.CrawlError as error:
        print("[ERROR] 无法访问学校官网：%s" % error)
        print("[ERROR] 请检查电脑是否已连接武汉理工大学校园网，然后重新运行。")
        return 1
    except Exception as error:
        print("[ERROR] 无法访问学校官网：%s" % error)
        traceback.print_exc()
        return 1

    print("[INFO] 成功获取通知列表，共发现 %d 条" % len(all_notices))

    if not all_notices:
        print("[ERROR] 一条通知都没抓到，可能是网站页面结构发生了变化。")
        return 1

    # ------------------------------------------------------
    # 第三步：时间筛选
    # ------------------------------------------------------
    in_window = crawler.filter_by_time(all_notices, cutoff_date)
    print("[INFO] 时间窗口内发布：%d 条" % len(in_window))

    # ------------------------------------------------------
    # 第四步：关键词筛选
    # ------------------------------------------------------
    matched = crawler.filter_by_keywords(in_window, config.KEYWORDS)
    print("[INFO] 关键词匹配成功：%d 条" % len(matched))

    # ------------------------------------------------------
    # 第五步：去掉以前已经发过的
    # ------------------------------------------------------
    fresh = state.remove_already_reported(matched, saved_state)
    print("[INFO] 其中真正的新通知：%d 条" % len(fresh))

    # ------------------------------------------------------
    # 第六步：排序（本科生院 → 信息学院 → 留学交换 → 其他按拼音首字母）
    # ------------------------------------------------------
    ordered = organizer.sort_notices(fresh)
    if ordered:
        print(organizer.describe_groups(ordered))
        for item in ordered:
            print("        · [%s] %s" % (item["date"].strftime("%Y-%m-%d"), item["title"]))

    # ------------------------------------------------------
    # 第七步：判断要不要发这封邮件
    # ------------------------------------------------------
    if not ordered and not config.SEND_WHEN_EMPTY:
        print("[INFO] 没有符合条件的新通知，按配置不发邮件。")
        # 虽然没发邮件，但这次检查是成功完成的，所以照样更新状态，
        # 免得下次运行又把同样的一段窗口重新抓一遍。
        state.save_state(run_time, saved_state["reported_urls"], [])
        print("[INFO] 程序运行结束。")
        return 0

    # ------------------------------------------------------
    # 第八步：生成邮件
    # ------------------------------------------------------
    subject = email_sender.build_subject(window_start, run_time, is_catchup)
    body = email_sender.build_body(ordered, window_start, run_time)

    # ------------------------------------------------------
    # 第九步：发送邮件
    # ------------------------------------------------------
    print("[INFO] 正在发送邮件...")
    try:
        email_sender.send_email(subject, body)
    except Exception as error:
        print("[ERROR] QQ邮箱发送失败：%s" % error)
        print("[ERROR] 以下是本次生成的邮件内容，你可以复制后手动发送：")
        print("-" * 60)
        print(body)
        print("-" * 60)
        print("[ERROR] 本次不更新状态文件，下次运行会自动重试这些通知。")
        return 1

    print("[SUCCESS] 邮件发送成功，收件邮箱：%s" % config.RECEIVER_EMAIL)

    # ------------------------------------------------------
    # 第十步：更新状态
    # ------------------------------------------------------
    state.save_state(run_time, saved_state["reported_urls"], ordered)

    print("[INFO] 程序运行结束。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
