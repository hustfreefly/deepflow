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
receivers = ["81240779@qq.com"]
files = [
    "/Users/allen/.openclaw/media/tool-image-generation/sem-gpt2-main---9570a519-9b82-4c43-90eb-c81b2105df5a.png",
]

msg = MIMEMultipart()
msg["From"] = sender
msg["To"] = ", ".join(receivers)
msg["Subject"] = Header("【SEM 主图】2.5D 封装截面（gpt-image-2 全景版，先看这版）", "utf-8")
msg.attach(MIMEText("""忠礼：

附件是昨晚出的 2.5D 封装 SEM 截面主图（gpt-image-2 文生图全景版，灰度，2.6MB PNG）。

看图要点（自上而下）：
• 左侧 ASIC 大 die / 中间 HBM 8 层堆叠（层间 µbump 可见）/ 右侧 PIC die + 最右光纤阵列单元
• die 下方：µbump 阵列（亮铜柱 + SnAg 焊帽，暗色底充胶）
• 硅转接板：TSV 铜柱（亮环 + 中心缝）
• RDL 连续铜线
• C4 大焊球（最亮，带晶粒斑驳 + 上下界面 IMC 锯齿边）
• ABF 积层：暗介质 + 亮铜线段 + 锥形激光孔
• 最底部：玻纤束横截面（圆点束）
• 左上角 2mm 标尺

定性：示意级主图，结构齐全、SEM 质感（BSE 亮度层级 + 噪点 + 扫描带纹）过关；但几何不是按真实设计值画的——µbump pitch 目前是按常规 ~40µm 摆的。

下一步：等你给真实 µbump pitch（先进节点 25-35µm / 混合键合 1-10µm 无焊帽直连），我按 skill 里固化的四层结构画法出几何精确版。

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

print("B3 sent OK")
print("total MB:", round(sum(os.path.getsize(p) for p in files) / 1024 / 1024, 1))
