# 修复 Tushare 日期查询问题（范围查询取最新）

## 修复目标
修复 `ensure_key_metrics()` 中 Tushare `daily_basic` 查询方式，从固定日期查询改为日期范围查询取最新记录。

## 根因分析
- `time.strftime("%Y%m%d")` 获取今天日期查询 Tushare
- 早上 9:01 AM A股还未开盘（开盘时间 9:30），无当天数据
- 周末/节假日也无数据
- 导致 `daily_basic` 返回空 DataFrame

## 验证数据
- `trade_date=20260424` (今天 9:01 AM) → 0 条 ❌
- `start_date=20260414, end_date=20260424` → 8 条，最新 20260423 ✅
- 20260423 数据: PE 168.47, 股价 105.98, PB 5.63, PS 12.61

## 修复方案
```python
# 1. 查询最近 10 天数据（而非固定某一天）
end_date = time.strftime('%Y%m%d')
start_date = (pd.Timestamp.now() - pd.Timedelta(days=10)).strftime('%Y%m%d')

df = pro.daily_basic(
    ts_code=self.company_code,
    start_date=start_date,
    end_date=end_date
)

# 2. 按日期降序，取最新一条
if df is not None and not df.empty:
    df = df.sort_values('trade_date', ascending=False)
    row = df.iloc[0]  # 最新记录
    trade_date = row.get('trade_date')  # e.g. "20260423"
```

## 修复范围
- core/data_manager_worker.py: ensure_key_metrics() 方法

## 验收标准
- [ ] 早上 9:00 运行能获取到数据（取昨天/最近交易日）
- [ ] 获取的数据包含正确的 trade_date 信息
- [ ] key_metrics.json 6/6 字段填充
- [ ] 无 pandas 导入错误

## 执行步骤
1. 修改 ensure_key_metrics 中的 Tushare 查询逻辑
2. 添加 pandas 导入（如需要）
3. 测试验证
4. 提交
