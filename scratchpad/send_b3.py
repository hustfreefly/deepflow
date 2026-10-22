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
base = "/Users/allen/.openclaw/workspace/projects/apec2026-vpd-ivr/deliverables"
files = [
    base + "/B3-专利布局与创新方向-v1.pdf",
    base + "/B3-专利布局与创新方向-v1.pptx",
    base + "/B3-专利布局-slides.html",
]

msg = MIMEMultipart()
msg["From"] = sender
msg["To"] = ", ".join(receivers)
msg["Subject"] = Header("【B3】星辰封装供电专利布局与创新方向（PDF+PPT+HTML）", "utf-8")
msg.attach(
    MIMEText(
        """忠礼：

B3 专利布局报告三件套：

1. B3-专利布局与创新方向-v1.pdf —— 手机阅读版（16 页）
2. B3-专利布局与创新方向-v1.pptx —— 可编辑版（597 个原生 shapes，投屏前建议 PowerPoint 对密卡页目检一遍）
3. B3-专利布局-slides.html —— 浏览器放映版

内容概要（4 个技术专家并行发散 34 个 idea → 收敛精选 15 张创新卡）：
• 四域覆盖：电路拓扑 4 / 封装结构 4 / 测试可靠性 4 / 设计方法 3
• 每个创新点带：原理一句话 / 新颖性论证（绕开 Intel 红区+学术先手）/ 可实现性 / 优先级（高 13 中 2）
• 与 C3 既有 11 创新点的关系全部标注（已在 C3#N / 加深 / 续篇），防止重复申请
• Q4 行动清单：6-8 件递交排序 + Intel 五件中国专利 FTO 逐 claim 比对流程 + 江城/高校 IP 归属前置条款

策略要点（E4 专利策略师）：核心层/防御层/公开层三层组合；发明+实用新型同日双报适用标准；哪些公开哪些商业秘密（学 TSMC：规则集本体商业秘密）。

至此今晚全部交付完成：主汇报 v2 PDF（修复版）+ B1 洞察 + B2 路线 + B3 专利布局。

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
