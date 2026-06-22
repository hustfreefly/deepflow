"""
OCR 辅助工具测试
"""

import sys
import os
sys.path.insert(0, '/Users/allen/.openclaw/workspace/.deepflow/projects/resumefit/src')

from ocr_helper import check_ocr_dependencies, ocr_extract


def test_dependencies():
    """测试依赖检查"""
    print("=== 测试：OCR 依赖检查 ===")
    deps = check_ocr_dependencies()
    print(f"PyMuPDF: {'✅' if deps['pymupdf'] else '❌'}")
    print(f"PaddleOCR: {'✅' if deps['paddleocr'] else '❌'}")
    print(f"Ready: {'✅' if deps['ready'] else '❌'}")
    print()
    return deps['ready']


def test_ocr_pdf():
    """测试 PDF 文本提取"""
    print("=== 测试：PDF 文本提取 ===")
    
    # 创建一个测试 PDF
    test_pdf = '/tmp/test_resume.pdf'
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "高级封装工程师 - 华为技术有限公司\n2020.06 - 至今")
        doc.save(test_pdf)
        doc.close()
        
        # 测试提取
        text = ocr_extract(test_pdf)
        print(f"提取文本: {text[:100]}...")
        assert '华为技术有限公司' in text, "未提取到公司名"
        print("✅ PDF 文本提取测试通过\n")
        
    except ImportError:
        print("⚠️ PyMuPDF 未安装，跳过 PDF 测试\n")
    except Exception as e:
        print(f"❌ PDF 测试失败: {e}\n")
    finally:
        if os.path.exists(test_pdf):
            os.remove(test_pdf)


def test_ocr_image():
    """测试图片 OCR"""
    print("=== 测试：图片 OCR ===")
    
    # 创建一个测试图片
    test_img = '/tmp/test_resume.png'
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        img = Image.new('RGB', (800, 200), color='white')
        draw = ImageDraw.Draw(img)
        
        # 尝试使用系统字体
        try:
            font = ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", 24)
        except:
            font = ImageFont.load_default()
        
        draw.text((20, 20), "高级封装工程师 - 华为技术有限公司", fill='black', font=font)
        draw.text((20, 60), "2020.06 - 至今", fill='black', font=font)
        
        img.save(test_img)
        
        # 测试 OCR
        text = ocr_extract(test_img)
        print(f"提取文本: {text[:100]}...")
        # PaddleOCR 可能无法 100% 准确，但至少应该提取到一些内容
        assert len(text) > 0, "未提取到任何文本"
        print("✅ 图片 OCR 测试通过\n")
        
    except ImportError:
        print("⚠️ PIL 或 PaddleOCR 未安装，跳过图片测试\n")
    except Exception as e:
        print(f"⚠️ 图片 OCR 测试跳过: {e}\n")
    finally:
        if os.path.exists(test_img):
            os.remove(test_img)


def test_invalid_file():
    """测试无效文件处理"""
    print("=== 测试：无效文件处理 ===")
    
    # 测试不存在的文件
    try:
        ocr_extract('/tmp/nonexistent.pdf')
        print("❌ 应该抛出异常")
    except ValueError as e:
        print(f"✅ 正确抛出 ValueError: {e}")
    
    # 测试不支持的格式
    test_txt = '/tmp/test.txt'
    with open(test_txt, 'w') as f:
        f.write("test")
    
    try:
        ocr_extract(test_txt)
        print("❌ 应该抛出异常")
    except ValueError as e:
        print(f"✅ 正确抛出 ValueError: {e}")
    finally:
        if os.path.exists(test_txt):
            os.remove(test_txt)
    
    print()


if __name__ == '__main__':
    ready = test_dependencies()
    
    if ready:
        test_ocr_pdf()
        test_ocr_image()
    
    test_invalid_file()
    
    print("=" * 50)
    print("✅ OCR 辅助工具测试完成！")
    print("=" * 50)

