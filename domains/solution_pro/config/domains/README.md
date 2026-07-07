# Solution Pro 领域配置目录

## 新增领域指南

1. 创建 `{domain_id}.yaml` 文件
2. 包含以下必需字段：domain_id, domain_label, meta_planner, expert_templates, seed_urls, output_structure
3. 参考 software.yaml 作为模板
4. 运行 validate_domain_config(domain_id) 验证

## 现有领域
- software.yaml — 软件开发（默认）
- investment.yaml — 投资分析
- hardware.yaml — 硬件设计
- business.yaml — 商业策略
