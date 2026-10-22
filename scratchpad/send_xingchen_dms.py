import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header

env = {}
with open("/Users/allen/.openclaw/workspace/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")

password = (
    env["SMTP_QQ_PASSWORD"] if "SMTP_QQ_PASSWORD" in env else env["SMTP_PASSWORD"]
)

sender = "81240779@qq.com"
receivers = ["zhongli_ji@hsingchen.com", "81240779@qq.com"]
base = "/Users/allen/.openclaw/workspace/projects/xingchen-dms"
files = [
    base + "/星辰文件管理系统四件套-20260929.zip",
]

msg = MIMEMultipart()
msg["From"] = sender
msg["To"] = ", ".join(receivers)
msg["Subject"] = Header(
    "【文件管理系统】封装设计团队文件管理系统四件套（审批PPT+手册+制度）", "utf-8"
)
msg.attach(
    MIMEText(
        """忠礼：

封装设计团队文件管理系统四件套，ZIP 打包见附件（解压密码无，直接打开）：

1. 架构梳理对齐-v0.md —— 业务边界/数据流/密级模型/演进路径（对齐用底稿）
2. Phase0-1落地手册-v1.md —— 部署照册执行：目录树/权限矩阵/SOP/命令+五轮核查加固（§11.5~11.9）
3. 安全审批-架构PPT-v2.pptx —— 3 页：业务泳道图开场 → 技术架构 → 安全控制+申请事项（拿这个见信息安全部门）
4. 附录A-文件服务器管理制度.md —— 一页纸六要素制度，交 IT/安全部门备案用

推荐使用顺序：先 PPT 第 1 页开场讲业务 → 第 2 页技术架构 → 第 3 页提出申请三事项 → 现场若被追问细节，手册 §4 审计/§7 脱敏/§8 外发 都是现成答案。

—— 小满
""",
        "plain",
        "utf-8",
    )
)

for path in files:
    with open(path, "rb") as f:
        part = MIMEApplication(f.read())
    fname = os.path.basename(path)
    part.add_header(
        "Content-Disposition", "attachment", filename=Header(fname, "utf-8").encode()
    )
    msg.attach(part)

ctx = ssl.create_default_context()
with smtplib.SMTP_SSL("smtp.qq.com", 465, context=ctx, timeout=90) as s:
    s.login(sender, password)
    s.sendmail(sender, receivers, msg.as_string())

print("B3 sent OK")
print("total MB:", round(sum(os.path.getsize(p) for p in files) / 1024 / 1024, 1))
