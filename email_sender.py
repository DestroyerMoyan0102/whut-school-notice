# -*- coding: utf-8 -*-
"""
email_sender.py —— 负责两件事：
  ① 把筛选出来的通知，整理成邮件正文（纯文本）
  ② 通过 QQ 邮箱的 SMTP 把邮件发出去

QQ 邮箱发信说明：
  - 服务器：smtp.qq.com
  - 加密方式 SSL，端口 465（本程序默认用这个）
  - 登录用的不是 QQ 密码，而是「SMTP 授权码」，
    在 QQ 邮箱网页版 -> 设置 -> 账号 -> 开启 SMTP 服务后拿到一串 16 位字符。
"""

import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate

import config


def build_subject(window_start, run_time, is_catchup=False):
    """
    生成邮件主题。

    - 日常运行（时间窗口约 24 小时）：【校园通知】过去24小时新增通知
    - 补跑（电脑关机/断网错过了，窗口超过 24 小时）：把真实日期范围写进主题，
      免得主题写「过去24小时」但实际补了 3 天的通知，看起来前后矛盾。
    """
    if not is_catchup:
        return "【校园通知】过去24小时新增通知"

    start_text = window_start.strftime("%m月%d日")
    end_text = run_time.strftime("%m月%d日")
    if start_text == end_text:
        return "【校园通知】%s 新增通知（补跑）" % end_text
    return "【校园通知】%s-%s 新增通知（补跑）" % (start_text, end_text)


def _format_time(moment):
    """把时间格式化成 2026年09月29日 20:00 这种中文写法。"""
    return moment.strftime("%Y年%m月%d日 %H:%M")


def build_body(notices, window_start, run_time):
    """
    按照约定的格式，拼出邮件正文。

    有通知时：
        武汉理工大学校园通知
        统计时间：…… ～ ……

        过去24小时内发现 X 条与我相关的通知。

        --------------------------------

        1. 通知标题

        发布时间：XXXX-XX-XX
        原文链接：URL

        --------------------------------

    没有通知时：
        武汉理工大学校园通知
        统计时间：…… ～ ……

        过去24小时内没有发现符合关键词条件的新通知。
    """
    lines = []
    lines.append("武汉理工大学校园通知")
    lines.append(
        "统计时间：%s ～ %s" % (_format_time(window_start), _format_time(run_time))
    )
    lines.append("")

    if not notices:
        lines.append("过去24小时内没有发现符合关键词条件的新通知。")
        return "\n".join(lines)

    lines.append("过去24小时内发现 %d 条与我相关的通知。" % len(notices))
    lines.append("")

    for index, item in enumerate(notices, start=1):
        lines.append("--------------------------------")
        lines.append("")
        lines.append("%d. %s" % (index, item["title"]))
        lines.append("")
        # 说明：学校网站只提供日期，没有具体时分，所以这里只输出到「日」
        lines.append("发布时间：%s" % item["date"].strftime("%Y-%m-%d"))
        lines.append("原文链接：%s" % item["url"])
        lines.append("")

    lines.append("--------------------------------")
    return "\n".join(lines)


def send_email(subject, body):
    """
    用 QQ 邮箱把邮件发出去。
    配置有问题、网络不通、授权码错误等等，都会抛出异常，由 main.py 捕获并打印提示。
    """
    # ---- 先检查配置是否完整，避免发出去了才报错 ----
    if not config.SENDER_EMAIL or "@" not in config.SENDER_EMAIL:
        raise ValueError("config.py 里的 SENDER_EMAIL（发件 QQ 邮箱）没有填写")
    if not config.SENDER_AUTH_CODE:
        raise ValueError(
            "没有找到 QQ 邮箱授权码。请设置环境变量 QQ_MAIL_AUTH_CODE，"
            "或在 config.py 里填写 SENDER_AUTH_CODE"
        )
    if not config.RECEIVER_EMAIL:
        raise ValueError("config.py 里的 RECEIVER_EMAIL（收件邮箱）没有填写")

    # ---- 组装邮件 ----
    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = formataddr(
        (str(Header(config.SENDER_NAME, "utf-8")), config.SENDER_EMAIL)
    )
    message["To"] = config.RECEIVER_EMAIL
    message["Date"] = formatdate(localtime=True)

    receivers = [addr.strip() for addr in config.RECEIVER_EMAIL.split(",") if addr.strip()]

    # ---- 连接 QQ 邮箱服务器并发送 ----
    if config.SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(
            config.SMTP_HOST, config.SMTP_PORT, timeout=config.REQUEST_TIMEOUT
        )
    else:
        server = smtplib.SMTP(
            config.SMTP_HOST, config.SMTP_PORT, timeout=config.REQUEST_TIMEOUT
        )
        server.starttls()

    try:
        server.login(config.SENDER_EMAIL, config.SENDER_AUTH_CODE)
        server.sendmail(config.SENDER_EMAIL, receivers, message.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            # 退出时的报错不重要，忽略掉，不要掩盖真正的发送错误
            pass
