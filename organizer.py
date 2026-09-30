# -*- coding: utf-8 -*-
"""
organizer.py —— 负责把筛选出来的通知「排好队」，决定它们在邮件里的先后顺序。

排序规则（可以在 config.py 的 PRIORITY_GROUPS 里改）：

    第 1 组  本科生院          ┐
    第 2 组  信息学院          │ 组内按「发布日期」从新到旧排
    第 3 组  留学交换          ┘
    第 4 组  其他（剩下全部）   按「拼音首字母」排

关于「拼音首字母排序」：
    Windows 自带的中文排序规则就是按拼音排的，Python 可以通过标准库 locale 用上它。
    实测效果：安 < 白 < 陈 < 董 < 高 < 李 < 欧阳 < 王 < 张 < 周 —— 正是拼音顺序。
    所以这里不需要安装拼音库（不用 pypinyin），零依赖。
"""

import locale

import config


def group_index_of(title):
    """
    判断一条通知属于第几组。
    返回 0 / 1 / 2 表示命中 config.PRIORITY_GROUPS 里的某一组；
    返回 len(PRIORITY_GROUPS) 表示哪一组都没命中，归入「其他」。
    """
    for index, group in enumerate(config.PRIORITY_GROUPS):
        for keyword in group.get("keywords", []):
            if keyword in title:
                return index
    return len(config.PRIORITY_GROUPS)


def _enable_pinyin_collation():
    """
    打开 Windows 的中文排序规则，让 locale.strxfrm 能按拼音排序汉字。
    成功返回 True，系统不支持时返回 False（程序会退回普通排序，不会崩）。
    """
    try:
        locale.setlocale(locale.LC_COLLATE, config.PINYIN_LOCALE)
        return True
    except locale.Error:
        print("[WARN] 系统不支持中文排序规则 %s，最后那一组改用普通排序" % config.PINYIN_LOCALE)
        return False


def sort_notices(notices):
    """
    把通知按规则排好序，返回一个新的列表。
    """
    other_index = len(config.PRIORITY_GROUPS)

    # 先按组分成几堆
    buckets = [[] for _ in range(other_index + 1)]
    for item in notices:
        buckets[group_index_of(item["title"])].append(item)

    sorted_notices = []

    # 前几组：组内按发布日期从新到旧
    for index in range(other_index):
        group_items = buckets[index]
        group_items.sort(key=lambda item: item["date"], reverse=True)
        sorted_notices.extend(group_items)

    # 最后一组「其他」：按拼音首字母
    others = buckets[other_index]
    if _enable_pinyin_collation():
        others.sort(key=lambda item: locale.strxfrm(item["title"]))
    else:
        others.sort(key=lambda item: item["title"])
    sorted_notices.extend(others)

    return sorted_notices


def describe_groups(notices):
    """
    生成一句用于终端提示的分组统计，例如：
        [INFO] 分组情况：本科生院 5 条 / 信息学院 1 条 / 留学交换 2 条 / 其他 8 条
    """
    other_index = len(config.PRIORITY_GROUPS)
    counts = [0] * (other_index + 1)
    for item in notices:
        counts[group_index_of(item["title"])] += 1

    parts = []
    for index, group in enumerate(config.PRIORITY_GROUPS):
        parts.append("%s %d 条" % (group.get("name", "第%d组" % (index + 1)), counts[index]))
    parts.append("其他 %d 条" % counts[other_index])

    return "[INFO] 分组情况：" + " / ".join(parts)
