#!/usr/bin/env python3
"""ResumeFit PDF + DOCX generator runner"""
import sys, json, os

# Add parent to path so 'src' is importable as package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Patch relative imports in pdf_renderer and docx_renderer
import importlib
import importlib.util

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Load interfaces first (no relative imports)
interfaces = load_module('src.interfaces', 'src/interfaces.py')
sys.modules['src'] = interfaces  # trick relative imports

# Now load other modules
pdf_mod = load_module('src.pdf_renderer', 'src/pdf_renderer.py')
docx_mod = load_module('src.docx_renderer', 'src/docx_renderer.py')
quality_mod = load_module('src.quality', 'src/quality.py')

from src.interfaces import (
    OptimizationResult, ResumeSection, ContentChange, 
    OptimizationLevel, RiskLevel, JDSchema, JDRequirement
)

# === Data ===
sections = [
    ResumeSection(
        title="姬忠礼",
        content="地点：上海 | 手机：13512100305 | 邮箱：81240779@qq.com",
        section_type="summary"
    ),
    ResumeSection(
        title="自我评价",
        content="芯片封装及仿真专家，15年+半导体封装经验，多年仿真团队管理经验。精通从芯片架构定义到量产交付的全链路封装技术，在异构集成、多芯片封装、2.5D/3D封装、芯片-封装-系统应力/翘曲仿真、热应力耦合与SI/PI协同优化、失效分析等领域有深厚积累。具备芯片/封装/板卡/服务器多尺度建模能力，有大颗FCBGA封装翘曲控制及上板应力/可靠性评估实战经验。技术敏感度高，拥有30+项中美发明专利。",
        section_type="summary"
    ),
    ResumeSection(
        title="核心优势",
        content="技术背景：封装仿真及封装工艺强技术背景，存储类封装强背景；熟悉芯片-封装-系统应力、翘曲仿真及热应力耦合分析方法。\n技术领导力：跨国团队协同，标准制定，专利布局，高校与产业界技术合作。\nAI创新：openclaw资深玩家，精通多个AI agent工具，已开发多agent协作引擎deepflow，实现高质量需求搜集-自动化输出高质量解决方案架构设计。（https://github.com/hustfreefly）\n仿真软件：ABAQUS、ANSYS Mechanical、Icepak、Flotherm、Moldflow、Moldex3D、SolidWorks（涵盖热应力仿真、多物理场协同及3D建模）",
        section_type="skills"
    ),
    ResumeSection(
        title="2021.12-至今 超聚变数字技术有限公司（杭州研究所） 主任工程师/实验室主任",
        content="（注：超聚变公司为原华为服务器业务部门，于2021年底从华为剥离）下属人数：3~5人\n工作职责和业绩：\n• 芯片封装设计与板级可靠性技术专家，负责SIP芯片封装设计与板级可靠性评估，负责计算产品线首款电源SIP类芯片封装设计到tR5阶段交付；芯片及模组在板应力和工艺可靠性评估，确保多款服务器产品交付。\n• 中央研究院建模仿真平台及AI基础设施负责人：搭建多物理场协同仿真平台（芯片-封装-板卡-系统多尺度建模），支撑公司芯片级/封装级/板级/服务器全链路SI/PI、热、应力仿真及热应力耦合分析，推进AI建模仿真应用。\n• 全球技术布局与知识产权：筹建海外研究所，主导硬工领域专利布局与知识产权建设。\n重点项目：\n• 字节全液冷AI服务器项目：AI芯片封装-板级应力-整机装联-机柜级可靠性分析评估，覆盖封装方案评估与材料选型，确保液冷服务器可靠性交付。",
        section_type="experience"
    ),
    ResumeSection(
        title="2019.12-2021.12 华为技术有限公司（上海研究所） 高级工程师",
        content="工作职责和业绩：\n• 芯片封装设计及可靠性：负责终端/数通/能源/计算产品线多个SIP异构集成项目的封装设计及仿真可靠性评估；鲲鹏大尺寸FCBGA芯片翘曲及上板应力/可靠性控制，板级工艺控制。\n• 先进封装工艺与散热技术：开发自有IP先进封装材料、工艺和方案（FOPOP、双面modeling），突破业界专利封锁；完成无线PAM模组大功率GaN散热优化设计、HBM 3D封装的散热设计优化。\n• 先进封装设备评估及工艺评估：TCB设备hybrid boding及NCF工艺。\n• 产学研技术合作：负责高校合作-SIP可靠性预测系统工程；参与IMEC/Fraunhofer-PLP、日研所-ABF PLP等下一代封装前沿项目，牵引技术演进。\n重点项目：\n• 终端SIP EMI攻关项目：突破业界专利封锁，开发自有EMI方案，并完成专利布局。\n• 参与华为鲲鹏芯片CPBI攻关，解决大尺寸芯片上板直通率问题，支撑芯片量产交付。\n• 国产MOS高可靠性封装架构优化：建立封装-器件协同设计标准，牵引多供应商封装设计优化及技术收敛，成功实现多款国产MOS导入。",
        section_type="experience"
    ),
    ResumeSection(
        title="2010.10-2019.11 Sandisk（上海）封装技术专家",
        content="下属人数：4人\n工作职责和业绩：\n• 先进封装仿真团队及实验室负责人：建立Sandisk上海存储封装芯片/模组相关应力可靠性、热、仿真工艺的仿真能力，支撑封装R&D及全球存储产品散热设计。\n• 先进封装工艺和技术开发：封装设计、封装基板选型、封装材料评估、封装工艺die bond/wire bond/modeling仿真、封装失效及可靠性评估；TSV/3D封装/Fanout技术研发，wafer warpage & die warpage控制。\n• 3D NAND异构集成研发：晶圆和芯片封装整合研发，联合Fab团队优化wafer设计及封装，确保芯片良率；闪存芯片/控制芯片新产品封装设计/材料/工艺评估（FC/FO/D2D bonding）。\n• 数字化仿真平台建设：开发封装仿真云计算平台，实现全自动仿真，搭建HPC集群，支撑全球团队仿真计算求解。\n• OSAT项目跟进：SPIL、PTi、Unimcron公司驻场跟进芯片封装良率，确保最终交付。\n• 产学研技术合作：负责美国高校合作stress die项目，实现芯片内部应力测试和仿真标定。\n重点项目：\n• 世界最高封装密度micro SD卡研发：实现16D堆叠、业界最薄die、单卡最高容量。\n• 封装仿真云计算平台开发：全自动仿真流程，获公司级奖项，至今稳定运行。\n• 负责筹建马来西亚海外封装工艺实验室及仿真团队。",
        section_type="experience"
    ),
    ResumeSection(
        title="2009.04-2010.10 上海电通欣普商务咨询公司 仿真工程师",
        content="工作职责：负责为KYOCERA公司打印机、复印机全系列工程仿真分析：整体结构-强度分析，关键部件热变形分析，模态、振动、噪声分析，流体散热仿真分析，刚体动力学仿真分析。",
        section_type="experience"
    ),
    ResumeSection(
        title="2008.05-2008.12 深圳康融通公司 CAE技术支持",
        content="工作职责：负责Solidworks simulation技术支持、培训及现场演示；针对客户不同分析需求制定相应CAE解决方案。仿真包含结构仿真和流体散热仿真。",
        section_type="experience"
    ),
    ResumeSection(
        title="2007.07-2007.11 富士康科技集团 仿真工程师",
        content="工作职责：电脑、手机连接器的仿真分析：仿真分析连接器的应力、应变、pin针变形及残余应变，及连接器保持力大小。",
        section_type="experience"
    ),
    ResumeSection(
        title="教育背景",
        content="2015.09–2021.06 上海交通大学 材料科学与工程 硕士\n2003.09–2007.07 华中科技大学 工程力学 本科（传热学、力学专业基础）",
        section_type="education"
    )
]

result = OptimizationResult(
    sections=sections,
    changes=[],
    fidelity_score=94.5,
    optimization_level=OptimizationLevel.STANDARD
)

# === Generate PDF ===
pdf_path = '/tmp/resumefit_tianshu.pdf'
pdf_output = pdf_mod.render_pdf(result, output_path=pdf_path, max_pages=2)
print(f"PDF: {pdf_output.file_path}, size={pdf_output.file_size_bytes}, ats={pdf_output.ats_compatible}")

# === Generate DOCX ===
docx_path = '/tmp/resumefit_tianshu.docx'
docx_output = docx_mod.render_docx(
    result, 
    output_path=docx_path,
    job_title="结构与热应力工程师",
    company_name="天数智芯"
)
print(f"DOCX: {docx_output.file_path}, size={docx_output.file_size_bytes}, editable={docx_output.editable}")

# === Quality Report ===
jd_schema = JDSchema(
    job_title="结构与热应力工程师",
    company="天数智芯",
    hard_requirements=[
        JDRequirement(text="芯片-封装-系统应力、翘曲仿真", category="skill", priority="must", weight=1.0),
        JDRequirement(text="封装方案评估、材料选型", category="skill", priority="must", weight=1.0),
        JDRequirement(text="热应力耦合仿真流程、多尺度建模", category="skill", priority="must", weight=1.0),
        JDRequirement(text="Bump/Ball应力仿真方法学", category="skill", priority="must", weight=1.0),
        JDRequirement(text="板卡结构可靠性评估", category="skill", priority="must", weight=1.0),
        JDRequirement(text="硕士及以上，机械/材料/力学", category="education", priority="must", weight=1.0),
        JDRequirement(text="封装、PCIE/OAM板卡结构、封装材料", category="experience", priority="must", weight=1.0),
        JDRequirement(text="传热学、力学", category="experience", priority="must", weight=1.0),
        JDRequirement(text="Ansys Mechanical, Flotherm, SolidWorks", category="skill", priority="must", weight=1.0),
        JDRequirement(text="FCBGA/2.5D/3D先进封装仿真经验", category="experience", priority="should", weight=0.8),
    ],
    soft_requirements=[
        JDRequirement(text="良好的沟通能力和学习能力", category="soft_skill", priority="should", weight=0.8),
    ],
    keywords=["应力仿真", "翘曲仿真", "热应力耦合", "封装方案评估", "材料选型", "多尺度建模", "Bump/Ball", "板卡结构可靠性", "FCBGA", "2.5D/3D先进封装", "Ansys Mechanical", "Flotherm", "SolidWorks", "传热学", "封装工艺"],
    confidence_score=0.93
)

report = quality_mod.generate_quality_report(jd_schema, result)
print(json.dumps({
    'overall': report.overall_score,
    'keyword': report.keyword_match,
    'experience': report.experience_match,
    'skill': report.skill_match,
    'education': report.education_match,
    'format': report.format_quality,
    'recommendations': report.recommendations
}, ensure_ascii=False))

