# -*- coding: utf-8 -*-
"""
state.py —— 记录「上次运行到哪儿了」，用来实现两件事：

  ① 补跑：电脑关机 / 断网错过了 12:00，下次开机时把前面漏掉的通知一起补上
  ② 去重：同一封通知不会因为「窗口有重叠」而被重复发第二次

状态文件是 state.json，就放在程序自己的文件夹里（D 盘），是一个很小的 JSON 文本文件，
不是数据库。里面长这样：

    {
      "last_run_time": "2026-09-30T12:00:05",
      "reported_urls": [
        "http://i.whut.edu.cn/xxtg/znbm/jwc/202609/t20260929_1420007.shtml",
        ...
      ]
    }

为什么要记「已发送过的链接」？
  因为学校网站只给日期、不给时分，所以时间窗口只能按「日期」算，必然会有重叠。
  比如 9-30 中午跑过一次，10-1 中午再跑，窗口起点是 9-30，
  那 9-30 当天上午已经发过的通知又会被抓进来一次。
  靠这个链接清单就能把它们过滤掉，只发真正的新通知。
"""

import json
import os
from datetime import datetime, timedelta

import config


def _empty_state():
    """没有状态文件时用的空状态。"""
    return {"last_run_time": None, "reported_urls": []}


def load_state():
    """
    读取状态文件。文件不存在、内容坏了、格式不对，都当成「第一次运行」处理，
    并且打印提示，不会让程序崩掉。
    """
    if not os.path.exists(config.STATE_FILE):
        print("[INFO] 没有找到状态文件，按第一次运行处理")
        return _empty_state()

    try:
        with open(config.STATE_FILE, "r", encoding="utf-8") as file_object:
            data = json.load(file_object)
    except Exception as error:
        print("[WARN] 状态文件读取失败，按第一次运行处理：%s" % error)
        return _empty_state()

    if not isinstance(data, dict):
        print("[WARN] 状态文件内容格式不对，按第一次运行处理")
        return _empty_state()

    raw_urls = data.get("reported_urls") or []
    if not isinstance(raw_urls, list):
        raw_urls = []

    return {
        "last_run_time": data.get("last_run_time"),
        "reported_urls": [item for item in raw_urls if isinstance(item, str)],
    }


def parse_last_run_time(state):
    """把状态里的时间字符串转成 datetime；转不出来就返回 None。"""
    text = state.get("last_run_time")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def compute_window_start(state, now):
    """
    算出这次要看「从什么时候开始」的通知。

    返回 (窗口起点, 是否属于补跑, 是否被上限截断)：
      - 第一次运行（没有状态）：窗口起点 = 当前时间 - 24 小时
      - 有状态：窗口起点 = 上次成功运行的时间
      - 如果上次运行距今超过 MAX_CATCHUP_DAYS 天，就把起点拉到那个上限，并标记「被截断」
    """
    is_first_run = False
    last_run = parse_last_run_time(state)

    if last_run is None:
        is_first_run = True
        window_start = now - timedelta(hours=config.HOURS_WINDOW)
    elif last_run > now:
        # 电脑时间被往回调过，兜底：当成刚跑过
        print("[WARN] 状态文件里的时间比当前时间还晚，按 24 小时窗口处理")
        is_first_run = True
        window_start = now - timedelta(hours=config.HOURS_WINDOW)
    else:
        window_start = last_run

    clamped = False
    earliest_allowed = now - timedelta(days=config.MAX_CATCHUP_DAYS)
    if window_start < earliest_allowed:
        window_start = earliest_allowed
        clamped = True

    # 超过 24 小时多一点，就认为这次是「补跑」而不是日常运行
    is_catchup = (now - window_start) > timedelta(hours=config.HOURS_WINDOW + 1)

    if is_first_run:
        print("[INFO] 第一次运行，时间窗口：过去 %d 小时" % config.HOURS_WINDOW)
    elif is_catchup:
        hours = round((now - window_start).total_seconds() / 3600, 1)
        print("[INFO] 距上次成功运行已过 %.1f 小时，本次为补跑，将补上漏掉的通知" % hours)

    if clamped:
        print(
            "[WARN] 距上次运行太久，已把回溯范围限制在最近 %d 天内（MAX_CATCHUP_DAYS）"
            % config.MAX_CATCHUP_DAYS
        )

    return window_start, is_catchup, clamped


def remove_already_reported(notices, state):
    """
    去掉「以前已经发过」的通知，避免重复发同一封通知。
    """
    already_sent = set(state.get("reported_urls") or [])
    if not already_sent:
        return list(notices)

    kept = [item for item in notices if item["url"] not in already_sent]
    removed_count = len(notices) - len(kept)
    if removed_count > 0:
        print("[INFO] 其中 %d 条以前已经发过，本次跳过" % removed_count)
    return kept


def save_state(now, old_urls, newly_reported_notices):
    """
    邮件发送成功之后，才更新状态文件：
      - last_run_time 改成现在
      - 把这次发过的链接追加进清单，并把清单截断到最近 MAX_KEEP_URLS 条

    注意：只有邮件真的发出去了才会调用这个函数。
    如果发信失败，状态不更新，下次运行还会把这些通知重新带上，不会丢。
    """
    merged = list(old_urls)
    for item in newly_reported_notices:
        merged.append(item["url"])

    # 只保留最后 MAX_KEEP_URLS 条
    merged = merged[-config.MAX_KEEP_URLS :]

    data = {
        "last_run_time": now.isoformat(timespec="seconds"),
        "reported_urls": merged,
    }

    # 先写临时文件再改名，避免写到一半失败把状态文件写坏
    temp_path = config.STATE_FILE + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as file_object:
            json.dump(data, file_object, ensure_ascii=False, indent=2)
        os.replace(temp_path, config.STATE_FILE)
        print("[INFO] 已更新状态文件：%s" % config.STATE_FILE)
    except Exception as error:
        print("[WARN] 状态文件写入失败（不影响本次邮件）：%s" % error)
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception:
            pass
