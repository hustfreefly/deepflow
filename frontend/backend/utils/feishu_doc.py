"""Feishu Doc API helper - create docx documents from markdown."""

import os
import re
import json
import requests
from typing import List, Dict, Any, Optional

# Feishu app credentials (from env or config)
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_USER_OPEN_ID = os.environ.get("FEISHU_USER_OPEN_ID", "")


def get_tenant_token() -> str:
    """Get Feishu tenant access token."""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {data}")
    return data["tenant_access_token"]


def create_document(title: str, token: str) -> str:
    """Create empty docx document. Returns document_id."""
    resp = requests.post(
        "https://open.feishu.cn/open-apis/docx/v1/documents",
        json={"title": title},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu create doc error: {data}")
    return data["data"]["document"]["document_id"]


def get_root_block_id(document_id: str, token: str) -> str:
    """Get root block id for a document."""
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu get blocks error: {data}")
    return data["data"]["items"][0]["block_id"]


def parse_markdown_to_blocks(content: str) -> List[Dict[str, Any]]:
    """Parse markdown lines into Feishu block structures."""
    blocks = []
    lines = content.split("\n")

    for line in lines:
        line = line.rstrip()
        if not line:
            continue

        # Heading 1
        if line.startswith("# "):
            text = line[2:].strip()
            blocks.append({
                "block_type": 3,
                "heading1": {
                    "elements": [{"text_run": {"content": text}}]
                }
            })
            continue

        # Heading 2
        if line.startswith("## "):
            text = line[3:].strip()
            blocks.append({
                "block_type": 4,
                "heading2": {
                    "elements": [{"text_run": {"content": text}}]
                }
            })
            continue

        # Heading 3
        if line.startswith("### "):
            text = line[4:].strip()
            blocks.append({
                "block_type": 5,
                "heading3": {
                    "elements": [{"text_run": {"content": text}}]
                }
            })
            continue

        # Bullet list - treat as text with bullet prefix for now
        if line.startswith("- ") or line.startswith("* "):
            text = "• " + line[2:].strip()
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": _parse_inline(text)
                }
            })
            continue

        # Numbered list - treat as text with number prefix for now
        numbered_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered_match:
            num = numbered_match.group(1)
            text = f"{num}. " + numbered_match.group(2)
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": _parse_inline(text)
                }
            })
            continue

        # Code block (fenced)
        if line.startswith("```"):
            # Skip code blocks for now (simplified)
            continue

        # Inline code
        if line.startswith("`") and line.endswith("`") and len(line) > 2:
            text = line[1:-1]
            blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [{"text_run": {"content": text, "text_element_style": {"inline_code": True}}}]
                }
            })
            continue

        # Regular text with inline formatting
        blocks.append({
            "block_type": 2,
            "text": {
                "elements": _parse_inline(line)
            }
        })

    return blocks


def _parse_inline(text: str) -> List[Dict[str, Any]]:
    """Parse inline markdown (bold, italic) into Feishu text_run elements."""
    elements = []
    # Pattern: **bold** or *italic* or plain text
    pattern = r"(\*\*([^*]+)\*\*|\*([^*]+)\*|([^*]+))"
    for match in re.finditer(pattern, text):
        if match.group(2):  # bold
            elements.append({
                "text_run": {
                    "content": match.group(2),
                    "text_element_style": {"bold": True}
                }
            })
        elif match.group(3):  # italic
            elements.append({
                "text_run": {
                    "content": match.group(3),
                    "text_element_style": {"italic": True}
                }
            })
        elif match.group(4):  # plain
            elements.append({
                "text_run": {"content": match.group(4)}
            })
    return elements if elements else [{"text_run": {"content": text}}]


def insert_blocks(document_id: str, root_block_id: str, blocks: List[Dict[str, Any]], token: str) -> None:
    """Insert blocks into document in batches of 50."""
    url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children"
    headers = {"Authorization": f"Bearer {token}"}

    for i in range(0, len(blocks), 50):
        batch = blocks[i:i+50]
        resp = requests.post(
            url,
            json={"children": batch},
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu insert blocks error: {data}")


def create_doc_from_markdown(title: str, content: str) -> str:
    """Create Feishu docx from markdown. Returns document URL."""
    token = get_tenant_token()
    doc_id = create_document(title, token)
    root_id = get_root_block_id(doc_id, token)
    blocks = parse_markdown_to_blocks(content)

    if blocks:
        insert_blocks(doc_id, root_id, blocks, token)

    return f"https://feishu.cn/docx/{doc_id}"


def send_doc_link_via_feishu_api(doc_url: str, title: str) -> dict:
    """Send document link directly via Feishu API (bypass OpenClaw CLI)."""
    try:
        token = get_tenant_token()
        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": FEISHU_USER_OPEN_ID,
                "msg_type": "text",
                "content": json.dumps({
                    "text": f"DeepFlow 分析报告：{title}\n{doc_url}"
                }, ensure_ascii=False),
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "success": data.get("code") == 0,
            "data": data,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
