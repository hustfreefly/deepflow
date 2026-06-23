#!/usr/bin/env python3
"""
DeepFlow 版本标识迁移脚本
为所有 prompt/cage/contract/domain 文件添加 YAML Front Matter 版本标识

执行:
    cd .deepflow && python3 scripts/migrate_version_headers.py

幂等: 已有 Front Matter 的文件会被跳过
"""

import sys
import re
import yaml
from pathlib import Path
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

DEEPFLOW_BASE = Path(__file__).resolve().parent.parent
TODAY = datetime.now().strftime("%Y-%m-%d")

# ============================================================
# 1. Prompt 文件迁移
# ============================================================

def migrate_prompts_from_registry():
    """为 registry.yaml 中注册的 prompt 文件补 Front Matter"""
    registry_path = DEEPFLOW_BASE / "prompts" / "registry.yaml"
    if not registry_path.exists():
        print("  ⚠ registry.yaml 不存在，跳过")
        return 0
    
    with open(registry_path) as f:
        registry = yaml.safe_load(f)
    
    migrated = 0
    for domain_name, domain_data in registry.get("domains", {}).items():
        for prompt_id, prompt_data in domain_data.get("prompts", {}).items():
            filename = prompt_data.get("filename", f"{prompt_id}.md")
            version = prompt_data.get("version", "1.0.0")
            role = prompt_data.get("role", "unknown")
            updated = prompt_data.get("updated", TODAY)
            
            filepath = DEEPFLOW_BASE / "prompts" / domain_name / filename
            if not filepath.exists():
                print(f"  ⚠ 文件不存在: {filepath.relative_to(DEEPFLOW_BASE)}")
                continue
            
            content = filepath.read_text(encoding="utf-8")
            if content.startswith("---"):
                continue  # 已有 Front Matter，跳过
            
            front_matter = (
                f"---\n"
                f"id: {domain_name}/{prompt_id}\n"
                f"version: \"{version}\"\n"
                f"component: {domain_name}\n"
                f"role: {role}\n"
                f"updated: \"{updated}\"\n"
                f"---\n\n"
            )
            filepath.write_text(front_matter + content, encoding="utf-8")
            migrated += 1
            print(f"  ✓ {domain_name}/{filename} → v{version}")
    
    return migrated


def migrate_unregistered_prompts():
    """为 prompts/ 下未在 registry 中注册的 domain 补 Front Matter"""
    unregistered_domains = ["architecture", "code", "general", "system"]
    migrated = 0
    
    for domain_name in unregistered_domains:
        domain_dir = DEEPFLOW_BASE / "prompts" / domain_name
        if not domain_dir.exists():
            continue
        
        for filepath in sorted(domain_dir.glob("*.md")):
            content = filepath.read_text(encoding="utf-8")
            if content.startswith("---"):
                continue
            
            front_matter = (
                f"---\n"
                f"id: {domain_name}/{filepath.stem}\n"
                f"version: \"1.0.0\"\n"
                f"component: {domain_name}\n"
                f"updated: \"{TODAY}\"\n"
                f"---\n\n"
            )
            filepath.write_text(front_matter + content, encoding="utf-8")
            migrated += 1
            print(f"  ✓ {domain_name}/{filepath.name} → v1.0.0")
    
    return migrated


# ============================================================
# 2. Cage 文件迁移
# ============================================================

def migrate_cage():
    """为 cage/active/ 下的 YAML 文件补全 cage_version 字段"""
    cage_dir = DEEPFLOW_BASE / "cage" / "active"
    if not cage_dir.exists():
        print("  ⚠ cage/active/ 不存在，跳过")
        return 0
    
    migrated = 0
    for filepath in sorted(cage_dir.glob("*.yaml")):
        content = filepath.read_text(encoding="utf-8")
        
        # 已有 cage_version 字段，跳过
        if re.search(r'^cage_version:', content, re.MULTILINE):
            continue
        # 已有 YAML front matter 且有 version，跳过
        if content.startswith("---"):
            try:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    meta = yaml.safe_load(parts[1])
                    if meta and ("cage_version" in meta or "version" in meta):
                        continue
            except Exception:
                logger.debug(f"migration step: {e}")
        
        # 从文件名推断版本
        m = re.search(r'_v(\d+\.\d+)', filepath.stem)
        version = f"{m.group(1)}.0" if m else "1.0.0"
        
        # 从文件名推断 component
        stem = filepath.stem
        m2 = re.match(r'^([a-z_]+?)_v', stem)
        component = m2.group(1) if m2 else stem
        
        # 在文件头部插入
        header = f"cage_version: \"{version}\"\ncomponent: {component}\nstatus: active\n"
        new_content = header + "\n" + content if not content.startswith("#") else header + content
        filepath.write_text(new_content, encoding="utf-8")
        migrated += 1
        print(f"  ✓ {filepath.name} → cage_version: {version}")
    
    return migrated


# ============================================================
# 3. Contract 文件迁移
# ============================================================

def migrate_contracts():
    """为 contracts/ 下的 .md 文件添加 Front Matter"""
    contracts_dir = DEEPFLOW_BASE / "contracts"
    if not contracts_dir.exists():
        print("  ⚠ contracts/ 不存在，跳过")
        return 0
    
    migrated = 0
    for filepath in sorted(contracts_dir.glob("*.md")):
        content = filepath.read_text(encoding="utf-8")
        if content.startswith("---"):
            continue
        
        # 尝试从内容中提取版本
        m = re.search(r'>\s*\*\*版本\*\*:\s*(\d+\.\d+\.\d+)', content)
        version = m.group(1) if m else "1.0.0"
        
        contract_id = filepath.stem
        front_matter = (
            f"---\n"
            f"id: contracts/{contract_id}\n"
            f"version: \"{version}\"\n"
            f"updated: \"{TODAY}\"\n"
            f"---\n\n"
        )
        filepath.write_text(front_matter + content, encoding="utf-8")
        migrated += 1
        print(f"  ✓ {filepath.name} → v{version}")
    
    return migrated


# ============================================================
# 4. Domain YAML 迁移
# ============================================================

def migrate_domains():
    """为 domains/*.yaml 添加 component_version"""
    domains_dir = DEEPFLOW_BASE / "domains"
    if not domains_dir.exists():
        print("  ⚠ domains/ 不存在，跳过")
        return 0
    
    migrated = 0
    
    # 顶层 domain YAML
    for filepath in sorted(domains_dir.glob("*.yaml")):
        content = filepath.read_text(encoding="utf-8")
        
        # 已有 component_version，跳过
        if re.search(r'^component_version:', content, re.MULTILINE):
            continue
        
        # 已有 front matter 且有 component_version，跳过
        if content.startswith("---"):
            try:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    meta = yaml.safe_load(parts[1])
                    if meta and "component_version" in meta:
                        continue
            except Exception:
                logger.debug(f"migration step: {e}")
        
        # 从内容中推断
        data = yaml.safe_load(content) or {}
        component_name = data.get("name", filepath.stem)
        domain = data.get("domain", filepath.stem)
        
        # 已有 version 字段就用，否则 1.0.0
        version = data.get("version", data.get("component_version", "1.0.0"))
        
        # 在 domain 字段前面插入 component_version
        if re.search(r'^domain:', content, re.MULTILINE):
            new_content = re.sub(
                r'^(domain:)',
                f'component_version: "{version}"\ncomponent_name: "{component_name}"\n\\1',
                content,
                count=1,
                flags=re.MULTILINE
            )
        else:
            new_content = f"component_version: \"{version}\"\ncomponent_name: \"{component_name}\"\n\n" + content
        
        filepath.write_text(new_content, encoding="utf-8")
        migrated += 1
        print(f"  ✓ {filepath.name} → component_version: {version}")
    
    # 各 domain 子目录下的 config/*.yaml
    for sub in sorted(domains_dir.iterdir()):
        if not sub.is_dir():
            continue
        config_dir = sub / "config"
        if not config_dir.exists():
            continue
        for cfg_file in sorted(config_dir.glob("*.yaml")):
            content = cfg_file.read_text(encoding="utf-8")
            if re.search(r'^(component_version|version):', content, re.MULTILINE):
                continue
            if content.startswith("---"):
                try:
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        meta = yaml.safe_load(parts[1])
                        if meta and ("component_version" in meta or "version" in meta):
                            continue
                except Exception:
                    logger.debug(f"migration step: {e}")
            
            data = yaml.safe_load(content) or {}
            domain_name = sub.name
            version = data.get("version", "1.0.0")
            component_name = data.get("name", domain_name.title())
            
            new_content = f"component_version: \"{version}\"\ncomponent_name: \"{component_name}\"\n\n" + content
            cfg_file.write_text(new_content, encoding="utf-8")
            migrated += 1
            print(f"  ✓ {sub.name}/config/{cfg_file.name} → component_version: {version}")
    
    return migrated


# ============================================================
# 5. CHANGELOG.md 更新
# ============================================================

def update_changelog(migration_summary: dict):
    """在 CHANGELOG.md 中添加版本迁移记录"""
    changelog_path = DEEPFLOW_BASE / "CHANGELOG.md"
    if not changelog_path.exists():
        print("  ⚠ CHANGELOG.md 不存在，跳过")
        return
    
    content = changelog_path.read_text(encoding="utf-8")
    
    # 检查是否已有此条目
    if "版本管理体系" in content or "Version Management" in content:
        print("  ⚠ CHANGELOG.md 已有版本迁移记录，跳过")
        return
    
    entry = f"""## [0.1.3] - {TODAY}

### Component Versions
- Spec Pro: 2.3.0
- Solution Pro: 3.2.0
- Investment: 2.0.0
- Research Pro: 1.0.0

### Added
- **版本管理体系**: 三层版本架构（全局/组件/文件级）
  - 所有 prompt/cage/contract/domain 文件添加 YAML Front Matter 版本标识
  - `prompt_registry.py`: `read_prompt()` 自动剥离 Front Matter
  - `prompt_registry.py`: `validate()` 从报 warning 改为版本一致性检查
  - 迁移脚本: `scripts/migrate_version_headers.py`

### Changed
- 修复 `master_agent.py` / `orchestrator_agent.py` 硬编码版本问题

---

"""
    
    # 在 ## [Unreleased] 之后插入
    new_content = content.replace(
        "## [Unreleased]",
        "## [Unreleased]\n\n" + entry
    )
    changelog_path.write_text(new_content, encoding="utf-8")
    print(f"  ✓ CHANGELOG.md 更新")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("DeepFlow 版本标识迁移")
    print(f"DeepFlow base: {DEEPFLOW_BASE}")
    print(f"日期: {TODAY}")
    print("=" * 60)
    
    total = 0
    
    print("\n[1/5] Prompt 文件迁移（已注册）...")
    n = migrate_prompts_from_registry()
    total += n
    print(f"  共迁移 {n} 个文件")
    
    print("\n[2/5] Prompt 文件迁移（未注册 domain）...")
    n = migrate_unregistered_prompts()
    total += n
    print(f"  共迁移 {n} 个文件")
    
    print("\n[3/5] Cage 文件迁移...")
    n = migrate_cage()
    total += n
    print(f"  共迁移 {n} 个文件")
    
    print("\n[4/5] Contract 文件迁移...")
    n = migrate_contracts()
    total += n
    print(f"  共迁移 {n} 个文件")
    
    print("\n[5/5] Domain YAML 迁移...")
    n = migrate_domains()
    total += n
    print(f"  共迁移 {n} 个文件")
    
    print(f"\n{'=' * 60}")
    print(f"迁移完成！共处理 {total} 个文件")
    print(f"{'=' * 60}")
    
    # 更新 CHANGELOG
    print("\n更新 CHANGELOG.md...")
    update_changelog({"total": total})
