"""
Spec Pro Upload Router - 需求文档上传端点

职责:
1. 接收用户上传的需求文档（.md/.txt）
2. 验证格式和大小
3. 调用 SpecExtractor 进行 LLM 提取
4. 返回结构化提取结果

红线:
- 不暴露凭证到前端
- 不修改 Solution Pro 核心代码
- LLM 提取失败不阻断流程
"""
import uuid
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, Form

from spec_extractor import SpecExtractor

router = APIRouter()

# ── 配置 ──

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".md", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ── 启动清理 ──


@router.on_event("startup")
async def cleanup_old_uploads():
    """启动时清理超过 24 小时的临时文件。"""
    cutoff = time.time() - 24 * 3600
    count = 0
    for f in UPLOAD_DIR.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                count += 1
            except OSError:
                pass
    if count > 0:
        print(f"[Upload] Cleaned up {count} old upload files")


# ── 端点 ──


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    solution_type: Optional[str] = Form(None),
):
    """
    上传需求文档，自动提取结构化需求。

    Args:
        file: 上传的文件（.md 或 .txt，最大 10MB）
        solution_type: 用户预选方案类型（可选）

    Returns:
        提取的结构化需求结果
    """
    # 验证文件扩展名
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 读取文件内容
    content = await file.read()

    # 验证文件大小
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件过大（{len(content) / 1024 / 1024:.1f}MB），最大允许 10MB",
        )

    # 验证非空
    if not content.strip():
        raise HTTPException(status_code=400, detail="文件内容为空")

    # 解码文本
    try:
        text = content.decode("utf-8-sig")  # utf-8-sig 自动去除 BOM
    except UnicodeDecodeError:
        try:
            text = content.decode("gbk")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400, detail="文件编码不支持，请使用 UTF-8 编码"
            )

    # 保存到临时文件（用于日志追踪）
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    temp_path = UPLOAD_DIR / safe_name
    with open(temp_path, "wb") as f:
        f.write(content)

    # 调用 LLM 提取
    extractor = SpecExtractor()
    try:
        result = extractor.extract_requirements(text, solution_type=solution_type)
    except Exception as e:
        # LLM 提取失败，降级返回原始文本
        result = {
            "topic": "",
            "solution_type": solution_type,
            "constraints": [],
            "stakeholders": [],
            "confidence": 0.0,
            "extracted_text": text[:5000],
            "error": str(e),
        }

    # 附加原始文本供前端预览
    result["extracted_text"] = text[:5000]

    return result
