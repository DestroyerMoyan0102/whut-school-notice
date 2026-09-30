# -*- coding: utf-8 -*-
"""
make_task_xml.py —— 生成 Windows 计划任务的描述文件 task.xml

它只做一件事：把「每天 12:00 运行 main.py，错过就补跑」这个任务写成 XML，
之后由 install_task.bat 交给系统的 schtasks 命令去注册。

为什么不直接写好一个固定的 XML，而要用 Python 现算？
  因为这个 XML 里有几样「每台电脑都不一样」的东西：
    1) Python 的安装路径（你的路径里含中文，手写容易出错、还容易编码乱码）
    2) 当前登录的 Windows 账号名
  交给 Python 自动读取并写入，就不会写错。
  XML 用 UTF-16 编码保存，这是 Windows 计划任务的标准编码。

生成出来的任务长这样：
    触发器：每天 12:00，每天一次
    补跑  ：StartWhenAvailable = true
            —— 如果 12:00 时电脑关着 / 在睡眠，开机后系统会尽快把这次补上
    重试  ：如果任务失败（比如当时没连校园网），每 15 分钟重试一次，最多 3 次
    电池  ：允许在使用电池时启动、也不因切换到电池而停止
            —— 笔记本默认是不允许的，这里特意打开，否则拔了电源就不跑了
    执行  ：<Python路径> main.py，工作目录就是本文件夹
"""

import os
import sys
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

TASK_NAME = "WHUT_SchoolNotice"

TEMPLATE = """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>武汉理工大学校园通知抓取与邮件提醒。每天 12:00 运行 main.py；若因关机或断网错过，会在电脑可用后尽快补跑。</Description>
    <URI>\\{task_name}</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
{principals}  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure>
      <Interval>PT15M</Interval>
      <Count>3</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>"{script_path}"</Arguments>
      <WorkingDirectory>{work_dir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    python_exe = sys.executable
    script_path = os.path.join(base_dir, "main.py")
    output_path = os.path.join(base_dir, "task.xml")

    if not os.path.exists(script_path):
        print("[ERROR] 找不到 main.py：%s" % script_path)
        return 1

    # 从明天 12:00 开始第一次自动运行（避免注册完立刻被当成「错过的任务」而马上跑一次）
    tomorrow = datetime.now() + timedelta(days=1)
    start_boundary = tomorrow.strftime("%Y-%m-%dT12:00:00")

    # 当前 Windows 账号，例如 LAPTOP-XXXX\莫妍
    domain = os.environ.get("USERDOMAIN", "").strip()
    username = os.environ.get("USERNAME", "").strip()
    if domain and username:
        user_id = "%s\\%s" % (domain, username)
        principals = (
            "  <Principals>\n"
            '    <Principal id="Author">\n'
            "      <UserId>%s</UserId>\n"
            "      <LogonType>InteractiveToken</LogonType>\n"
            "      <RunLevel>LeastPrivilege</RunLevel>\n"
            "    </Principal>\n"
            "  </Principals>\n" % escape(user_id)
        )
    else:
        # 读不到账号名就不写这段，让系统默认用当前用户
        principals = ""
        print("[WARN] 读不到当前 Windows 账号名，任务将默认使用当前登录用户")

    xml_text = TEMPLATE.format(
        task_name=escape(TASK_NAME),
        start_boundary=start_boundary,
        principals=principals,
        python_exe=escape(python_exe),
        script_path=escape(script_path),
        work_dir=escape(base_dir),
    )

    # UTF-16 是 Windows 计划任务 XML 的标准编码
    with open(output_path, "w", encoding="utf-16") as file_object:
        file_object.write(xml_text)

    print("[OK] 已生成：%s" % output_path)
    print("     Python  : %s" % python_exe)
    print("     脚本    : %s" % script_path)
    print("     首次运行: %s 12:00" % tomorrow.strftime("%Y-%m-%d"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
