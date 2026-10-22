import zipfile, shutil, os, re

SRC_DIR = "/Users/allen/.openclaw/workspace/projects/apec2026-vpd-ivr/deliverables"
JOBS = [
    ("B1-垂直供电-深度洞察报告-v1.pptx", "B1-垂直供电-深度洞察报告-print.pptx"),
    ("B2-如果我们做-行动路线报告-v1.pptx", "B2-如果我们做-行动路线报告-print.pptx"),
]
TARGET = "Noto Sans CJK SC"

for src_name, dst_name in JOBS:
    src = os.path.join(SRC_DIR, src_name)
    dst = os.path.join(SRC_DIR, dst_name)
    zin = zipfile.ZipFile(src, "r")
    zout = zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED)
    count = 0
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.endswith(".xml"):
            text = data.decode("utf-8", "ignore")
            # 替换显式 PingFang SC
            new = text.replace('typeface="PingFang SC"', 'typeface="%s"' % TARGET)
            # 主题东亚字体位（+mn-ea / +mj-ea 的实体定义）
            new = re.sub(
                r'(<a:ea typeface=")PingFang SC(")', r"\g<1>%s\g<2>" % TARGET, new
            )
            if new != text:
                count += text.count('typeface="PingFang SC"')
            data = new.encode("utf-8")
        zout.writestr(item, data)
    zin.close()
    zout.close()
    print(dst_name, "replaced:", count)
print("patch done")
