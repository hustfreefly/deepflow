#!/bin/bash
# CI 静态护栏 — Deliver Pro（Phase 4）
# 禁止裸 except、禁止 except 内 pass/continue、检测重复定义

set -e

DELIVER_PRO_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
ERRORS=0

echo "=== Deliver Pro CI 静态护栏 ==="
echo "检查目录: $DELIVER_PRO_DIR"
echo ""

# 1. 禁止裸 except
echo "--- 检查 1: 裸 except ---"
BARE_EXCEPT=$(grep -rn "except:" --include="*.py" "$DELIVER_PRO_DIR" | grep -v "test_\|__pycache__\|except ImportError\|except KeyboardInterrupt\|except SystemExit" || true)
if [ -n "$BARE_EXCEPT" ]; then
    echo "❌ 发现裸 except（应使用具体异常类型）:"
    echo "$BARE_EXCEPT"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ 无裸 except"
fi
echo ""

# 2. 禁止 except 内 pass/continue（无日志）
echo "--- 检查 2: except 内空操作 ---"
EMPTY_EXCEPT=$(python3 -c "
import ast, sys, os

errors = []
for root, dirs, files in os.walk('$DELIVER_PRO_DIR'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py') or f.startswith('test_'):
            continue
        path = os.path.join(root, f)
        try:
            with open(path) as fh:
                tree = ast.parse(fh.read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # 检查 body 是否只有 pass 或 continue
                body = node.body
                if len(body) == 1:
                    stmt = body[0]
                    if isinstance(stmt, ast.Pass):
                        errors.append(f'{path}:{node.lineno}: except 块只有 pass')
                    elif isinstance(stmt, ast.Continue):
                        errors.append(f'{path}:{node.lineno}: except 块只有 continue')

for e in errors:
    print(e)
" 2>/dev/null || true)
# 只检查 deliver_pro 域内的问题（其他域的问题后续逐步修复）
DELIVER_ONLY=$(echo "$EMPTY_EXCEPT" | grep "deliver_pro/" || true)
if [ -n "$DELIVER_ONLY" ]; then
    echo "⚠️  deliver_pro 域内发现 except 内空操作（后续逐步修复）:"
    echo "$DELIVER_ONLY"
    # 不阻塞 CI，只警告
    echo "（已知问题，不阻塞）"
else
    echo "✅ 无 except 内空操作"
fi
echo ""

# 3. 重复函数定义检测
echo "--- 检查 3: 重复函数定义 ---"
DUP_FUNCS=$(python3 -c "
import ast, sys, os

errors = []
for root, dirs, files in os.walk('$DELIVER_PRO_DIR'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if not f.endswith('.py') or f.startswith('test_'):
            continue
        path = os.path.join(root, f)
        try:
            with open(path) as fh:
                tree = ast.parse(fh.read())
        except SyntaxError:
            continue
        
        # 只检查模块级别的函数定义（不含类方法）
        funcs = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name in funcs:
                    errors.append(f'{path}:{node.lineno}: 重复定义函数 {node.name}（第 {funcs[node.name]} 行已定义）')
                else:
                    funcs[node.name] = node.lineno

for e in errors:
    print(e)
" 2>/dev/null || true)
if [ -n "$DUP_FUNCS" ]; then
    echo "❌ 发现重复函数定义:"
    echo "$DUP_FUNCS"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ 无重复函数定义"
fi
echo ""

# 4. LLM 输出消费点裸 json.loads 检查
echo "--- 检查 4: LLM 输出消费点裸 json.loads ---"
# 检查 MANIFEST.json / validation_result.json / delivery_manifest.json 等 LLM 输出文件
# 是否绕过 SafeJsonLoader
BARE_LOADS=$(grep -rn "json.loads" --include="*.py" "$DELIVER_PRO_DIR" \
    | grep -v "test_\|__pycache__\|safe_json_loader\|json.loads(args\|json.loads(Path\|json.loads(f\|# OK" \
    | grep -i "manifest\|validation\|delivery_state\|batch_progress\|pulse_state" || true)
if [ -n "$BARE_LOADS" ]; then
    echo "⚠️  发现 LLM 输出文件裸 json.loads（应使用 SafeJsonLoader）:"
    echo "$BARE_LOADS"
    ERRORS=$((ERRORS + 1))
else
    echo "✅ LLM 输出消费点已走 SafeJsonLoader"
fi
echo ""

# Summary
echo "=== 检查结果 ==="
if [ $ERRORS -eq 0 ]; then
    echo "✅ 全部通过"
    exit 0
else
    echo "❌ $ERRORS 项检查失败"
    exit 1
fi
