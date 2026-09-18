import os, smtplib, ssl
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

password = env["SMTP_QQ_PASSWORD"] if "SMTP_QQ_PASSWORD" in env else env["SMTP_PASSWORD"]

sender = "81240779@qq.com"
receivers = ["zhongli_ji@hsingchen.com", "81240779@qq.com"]
base = "/Users/allen/.openclaw/workspace/projects/apec2026-vpd-ivr/deliverables"
files = [
    base + "/B1-垂直供电-深度洞察报告-v1.pdf",
    base + "/B2-如果我们做-行动路线报告-v1.pdf",
]

msg = MIMEMultipart()
msg["From"] = sender
msg["To"] = ", ".join(receivers)
msg["Subject"] = Header("【PDF版】B1 深度洞察报告 + B2 行动路线报告", "utf-8")
msg.attach(MIMEText("""忠礼：

你要的两份 PDF 版：

1. B1-垂直供电-深度洞察报告-v1.pdf（14 页）—— 技术×市场×应用×趋势四幕洞察
2. B2-如果我们做-行动路线报告-v1.pdf（15 页）—— 切入点裁决：五维尺/五条死法/错位主干/研发×合作清单

说明：PPTX→PDF 的 LibreOffice 直转链中文渲染损坏（今晨又试了一次字体补丁+清缓存无效），这两份 PDF 是按蓝图用 HTML 重建后 Chrome 渲染的——内容与 PPTX 完全一致，中文已目检确认零缺陷。要改内容仍改 PPTX 版即可。

至此四份报告全部都有 PDF 手机版了：主汇报 v2 + B1 + B2 + B3。

—— 小满
""", "plain", "utf-8"))

for path in files:
    with open(path, "rb") as f:
        part = MIMEApplication(f.read())
    fname = os.path.basename(path)
    part.add_header("Content-Disposition", "attachment", filename=Header(fname, "utf-8").encode())
    msg.attach(part)

ctx = ssl.create_default_context()
with smtplib.SMTP_SSL("smtp.qq.com", 465, context=ctx, timeout=90) as s:
    s.login(sender, password)
    s.sendmail(sender, receivers, msg.as_string())

print("B1B2 PDF sent OK")
print("total MB:", round(sum(os.path.getsize(p) for p in files) / 1024 / 1024, 1))
