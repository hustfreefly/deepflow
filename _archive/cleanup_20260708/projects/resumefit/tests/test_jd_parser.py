"""测试 JD 解析模块"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.interfaces import JDInput, JDInputType, JDSchema
from src.jd_parser import parse_jd, parse_text_jd, _extract_job_title, _extract_company

def test_text_jd_parsing():
    """测试文本 JD 解析"""
    jd_content = """
职位名称: 高级Python开发工程师
公司: 科技有限公司
要求:
- 必须精通Python，3年以上开发经验
- 熟悉Django/Flask框架
- 本科及以上学历
- 优先考虑有AI/ML经验者
- 良好的沟通能力和团队协作精神
- 加分项: 熟悉Docker和Kubernetes
"""
    jd_input = JDInput(content=jd_content, input_type=JDInputType.TEXT)
    schema = parse_jd(jd_input)

    assert isinstance(schema, JDSchema), "Output must be JDSchema"
    assert schema.job_title, "Job title must be extracted"
    print(f"  ✓ Job title: {schema.job_title}")
    print(f"  ✓ Company: {schema.company}")
    print(f"  ✓ Hard requirements: {len(schema.hard_requirements)}")
    print(f"  ✓ Soft requirements: {len(schema.soft_requirements)}")
    print(f"  ✓ Keywords: {schema.keywords}")
    print(f"  ✓ Weight matrix: {schema.weight_matrix}")
    print(f"  ✓ Confidence: {schema.confidence_score}")
    assert schema.confidence_score > 0, "Confidence must be > 0"
    print("  ✓ All assertions passed!")

def test_empty_jd():
    """测试空 JD 处理"""
    jd_input = JDInput(content="", input_type=JDInputType.TEXT)
    schema = parse_jd(jd_input)
    assert isinstance(schema, JDSchema)
    assert schema.confidence_score > 0
    print("  ✓ Empty JD handled gracefully")

def test_job_title_extraction():
    """测试职位提取"""
    text = "职位名称: 高级前端工程师\n公司: 某科技公司"
    title = _extract_job_title(text)
    assert "前端" in title or "工程师" in title, f"Expected engineer in title, got: {title}"
    print(f"  ✓ Job title extracted: {title}")

if __name__ == '__main__':
    print("=== Test JD Parser ===")
    test_text_jd_parsing()
    test_empty_jd()
    test_job_title_extraction()
    print("\n=== All JD Parser tests passed! ===")

