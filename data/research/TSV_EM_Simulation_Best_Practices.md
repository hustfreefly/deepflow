# TSV寄生参数提取与3D EM建模技术调研

> **文档类型**: 技术调研报告
> **关联任务**: T-001 | WP: SPI-002
> **调研日期**: 2026-07-29
> **覆盖 AC**: AC-1, AC-2, AC-3, AC-4, AC-5

---

## 目录

1. [全波求解器在TSV建模中的应用](#1-全波求解器在tsv建模中的应用)
2. [TSV RLCG等效电路提取流程](#2-tsv-rlcg等效电路提取流程)
3. [TSV阵列耦合分析方法](#3-tsv阵列耦合分析方法)
4. [TSV-RDL过渡结构建模技术](#4-tsv-rdl过渡结构建模技术)
5. [IBIS-AMI联合仿真方法](#5-ibis-ami联合仿真方法)
6. [56Gbps PAM4信号完整性评估标准](#6-56gbps-pam4信号完整性评估标准)
7. [参考文献](#参考文献)

---

## 1. 全波求解器在TSV建模中的应用

### 1.1 行业主流全波求解器

TSV（Through-Silicon Via）的电磁建模需要精确求解Maxwell方程组，行业主流工具包括：

| 求解器 | 厂商 | 核心算法 | 适用场景 |
|--------|------|----------|----------|
| **ANSYS HFSS** | Ansys | 有限元法（FEM） | 通用3D全波仿真，TSV阵列建模 |
| **CST Studio Suite** | Dassault Systèmes | 有限积分法（FIT） | 宽带时域/频域分析，封装级仿真 |
| **Cadence Clarity 3D** | Cadence | 自适应FEM | 大规模3D结构，分布式求解 |
| **Keysight ADS EMPro** | Keysight | FEM/FDTD | 与电路仿真紧密集成 |

### 1.2 HFSS在TSV建模中的设置方法

**建模流程**（来源：Georgia Tech Epsilon Lab, IEEE EPEPS 2011; MDPI Micromachines 2024）：

1. **几何建模**：
   - 创建圆柱形TSV结构，包含Cu填充柱、SiO₂绝缘层（厚度通常50-200nm）、Si衬底
   - 精确设置TSV直径（5-150μm）、高度（20-200μm）、间距（pitch）参数
   - 包含焊盘（pad）和底部RDL连接结构

2. **材料属性定义**：
   - Cu电导率：5.8×10⁷ S/m（考虑表面粗糙度修正）
   - SiO₂：εr=3.9，损耗角正切tanδ=0.001
   - Si衬底：εr=11.9，电导率依赖于掺杂浓度（典型10 S/m用于高阻硅）

3. **边界条件与激励**：
   - 波端口（Wave Port）激励设置在TSV两端，进行去嵌（de-embedding）至参考面
   - 辐射边界（Radiation Boundary）设置在模型外部
   - 对TSV阵列，使用周期性边界（Periodic Boundary）加速仿真

4. **网格设置**：
   - 自适应网格细化（Adaptive Mesh Refinement），目标ΔS < 0.02
   - 对氧化物薄层使用手动网格细化，确保至少2层网格穿过绝缘层
   - 对趋肤效应区域（skin depth）进行网格加密

5. **频率扫描**：
   - 宽带扫描：DC至100GHz（覆盖56Gbps PAM4的Nyquist频率28GHz及三次谐波84GHz）
   - 插值扫描（Interpolating Sweep）用于快速宽带S参数获取

### 1.3 CST在TSV建模中的设置方法

**CST Microwave Studio设置要点**（来源：IMAPS 2023, Micromachines 2024）：

1. **时域求解器（T- solver）**：
   - 推荐用于宽带TSV分析，天然适合时域反射（TDR）分析
   - 六面体网格（Hexahedral Mesh）对TSV圆柱结构更高效

2. **频域求解器（F- solver）**：
   - 用于窄带分析或需要精确频域结果的场景
   - 支持MIS结构的非线性电容建模

3. **关键设置**：
   - 波导端口（Waveguide Port）尺寸需覆盖TSV周围至少3×直径
   - 开放边界（Open Boundary）使用PML（Perfectly Matched Layer）吸收边界
   - 自适应网格细化目标：S参数误差 < 0.5%

### 1.4 Cadence Clarity 3D Solver

Clarity 3D Solver采用分布式自适应FEM，适合大规模TSV阵列（如HBM接口中的数千个TSV）的并行求解。其优势在于：
- 支持云/集群分布式计算
- 自适应网格减少了人工调参
- 与Cadence Virtuoso/Allegro平台紧密集成

---

## 2. TSV RLCG等效电路提取流程

### 2.1 行业标准提取流程

TSV的RLCG等效电路提取遵循以下标准流程（来源：JPier 2015, Georgia Tech GTCAD 2014, WSEAS 2014）：

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 3D EM建模    │───▶│ S参数提取     │───▶│ 去嵌处理      │───▶│ RLCG参数转换  │
│ (HFSS/CST)  │    │ (宽带扫描)    │    │ (TRL/T矩阵)   │    │              │
└─────────────┘    └──────────────┘    └──────────────┘    └──────┬───────┘
                                                                   │
┌─────────────┐    ┌──────────────┐    ┌──────────────┐           │
│ SPICE网表    │◀───│ 等效电路构建   │◀───│ 参数验证      │◀──────────┘
│ 生成         │    │ (π型/T型)     │    │ (vs全波仿真)  │
└─────────────┘    └──────────────┘    └──────────────┘
```

### 2.2 S参数到RLCG的转换方法

**TRL（Through-Reflect-Line）去嵌技术**（来源：NTHU EPEPS 2011）：

1. 设计TSV测试结构（Through/Reflect/Line标准件）
2. 测量/仿真S参数并转换为T矩阵
3. 级联去嵌，提取TSV本征S参数
4. 从S参数提取传播常数γ和特征阻抗Z₀
5. 计算RLCG：

```
R = Re(γ × Z₀)          [Ω/m]
L = Im(γ × Z₀) / ω      [H/m]
G = Re(γ / Z₀)          [S/m]
C = Im(γ / Z₀) / ω      [F/m]
```

**替代方法**（来源：Tsinghua University J. Semiconductors 2015）：
- 直接使用HFSS/Q3D的寄生参数提取功能
- 基于Y参数（导纳参数）的π型等效电路拟合
- 多项式拟合RLCG的频率依赖特性

### 2.3 等效电路拓扑选择

| 拓扑 | 适用条件 | 精度 | 复杂度 |
|------|----------|------|--------|
| 单π型 | 电长度 < λ/10 | 低频适用 | 低 |
| 级联π型 (N段) | 电长度 > λ/10 | 中高频 | 中 |
| 分布式传输线 | 任意电长度 | 全频带 | 高 |
| MOS电容模型 | 需考虑半导体效应 | 精确 | 高 |

**关键参数提取式**（来源：WSEAS CISSPA 2014, Georgia Tech DAC 2014）：

- **TSV电阻 R**：R = ρ·L/(π·r²) × K_skin(f)，其中K_skin为趋肤效应修正因子
- **TSV电感 L**：L = (μ₀·L/(2π)) × [ln(2L/r) - 1 + r/L]，内部自感≈μ₀·L/(8π)
- **TSV氧化层电容 C_ox**：C_ox = 2π·ε₀·ε_ox·L/ln(r_ox/r)
- **耗尽层电容 C_dep**：C_dep = 2π·ε₀·ε_Si·L/ln(r_dep/r_ox)，电压依赖
- **硅衬底电导 G_Si**：G_Si = 2π·σ_Si·L/ln(r_Si/r_dep)

### 2.4 频率依赖与电压依赖建模

TSV的MIS（Metal-Insulator-Semiconductor）结构导致电容具有电压依赖性（来源：MDPI Micromachines 2024, IEEE TED 2009）：

- **积累区**（Accumulation）：C_TSV ≈ C_ox（最大电容）
- **耗尽区**（Depletion）：C_TSV = C_ox ∥ C_dep（串联降低）
- **反型区**（Inversion）：C_TSV ≈ C_ox（高频时恢复）

MOS电容效应在高速信号（>1GHz）时尤为关键，因为信号摆幅经过不同工作区时，等效电容会动态变化。

---

## 3. TSV阵列耦合分析方法

### 3.1 耦合分析的重要性

在3D-IC中，TSV阵列间距可小至40-50μm，导致显著的电磁耦合（来源：Georgia Tech ISQED 2011, IBM Research 2011）。耦合效应主要表现为：

- **TSV-to-TSV电容耦合**：通过硅衬底的寄生电容路径
- **TSV-to-TSV电感耦合**：相邻TSV的互感导致串扰
- **慢波效应**（Slow-Wave Effect）：在低阻硅衬底中，电磁波传播速度降低

### 3.2 分析工具与方法

**全波仿真方法**（来源：Georgia Tech 2011, URSI 2014）：

1. **多端口S参数仿真**：
   - 在HFSS/CST中建立N-TSV阵列模型
   - 提取完整N×N S参数矩阵
   - 分析近端串扰（S31, S41）和远端串扰（S42, S43）

2. **多导体传输线（MTL）模型**：
   - 提取每单位长度的RLCG矩阵
   - 求解MTL电报方程，获得串扰传递函数
   - 计算FEXT（远端串扰）和NEXT（近端串扰）

3. **等效电路+全波混合方法**（来源：KAIST, ResearchGate 2011）：
   - 使用全波仿真提取耦合参数
   - 构建包含互容Cm和互感Lm的SPICE兼容网表
   - 在时域进行瞬态分析，验证串扰时序

### 3.3 耦合抑制策略

| 策略 | 方法 | 效果 | 代价 |
|------|------|------|------|
| 接地TSV屏蔽 | 在信号TSV间插入GND TSV | 耦合降低10-20dB | 面积增加 |
| 同轴TSV | 用接地环包围信号TSV | 耦合降低>30dB | 工艺复杂 |
| 差分信号 | 使用差分对传输 | 共模抑制 | 引脚数翻倍 |
| 编码方案 | 3D-CAM等编码技术 | 避免最差串扰模式 | 编码开销 |
| 增大间距 | 增加TSV pitch | 直接有效 | 面积成本 |

### 3.4 串扰量化指标

- **近端串扰比（NEXT）**：S31(dB) @ 14GHz（56Gbps PAM4基频）
- **远端串扰比（FEXT）**：S41(dB) @ 28GHz（Nyquist频率）
- **综合串扰噪声**：在时域测量耦合噪声电压峰值 < 5% · V_swing

---

## 4. TSV-RDL过渡结构建模技术

### 4.1 RDL（Redistribution Layer）概述

RDL是2.5D/3D封装中用于重新分布I/O焊盘位置的金属布线层（来源：IMAPS 2015, Cadence 2024）。TSV-RDL过渡结构是3D-IC中垂直互联与水平布线的关键接口。

**典型结构层次**：
```
     Chip Pad
        │
  ┌─────┴─────┐
  │  Top RDL   │  ← 微带线/带状线（Cu，厚度1-5μm）
  └─────┬─────┘
        │
  ┌─────┴─────┐
  │    TSV     │  ← 垂直互联（Cu填充，直径5-150μm）
  └─────┬─────┘
        │
  ┌─────┴─────┐
  │ Bottom RDL │  ← 底部布线层
  └─────┬─────┘
        │
     Bump/Pad
```

### 4.2 过渡结构EM建模挑战

**多尺度问题**（来源：IMAPS 2023, Georgia Tech 2015）：
- TSV直径（μm级）vs RDL线宽（亚μm-μm级）vs 氧化物厚度（nm级）
- 需要跨6个数量级尺度建模
- 网格密度差异巨大，需要分区域网格策略

**建模方法**：

1. **全波3D EM一体化建模**（来源：IMAPS 2023, MDPI Electronics 2025）：
   - 在HFSS/CST中建立完整的TSV+RDL+Pad+Via结构
   - 使用混合网格：TSV区用四面体网格，RDL平面区用棱柱网格
   - 频率范围：DC至100GHz

2. **分段建模+级联方法**（来源：Georgia Tech 2015）：
   - TSV段：用RLCG传输线模型
   - RDL段：用微带线模型（特征阻抗50Ω）
   - 过渡段：用全波S参数表征的不连续性
   - 级联S参数获得整体通道响应

3. **参数化扫描优化**（来源：MDPI Electronics 2025）：
   - TSV半径：2.5-25μm
   - RDL线宽：1-20μm
   - RDL间距：2-40μm
   - 衬底材料：Si vs Glass interposer

### 4.3 RDL优化设计准则

| 参数 | 推荐范围 | 对性能影响 |
|------|----------|-----------|
| RDL线宽/间距 | 1-5μm / 1-5μm | 控制阻抗和串扰 |
| RDL厚度 | 1-3μm | 影响导体损耗 |
| 过渡Via尺寸 | 与TSV直径匹配 | 减少反射 |
| 多层RDL | 2-4层 | 降低插入损耗，改善回波损耗 |

研究表明多层RDL设计可有效抵消TSV引入的插入损耗，并降低回波损耗（来源：MDPI Electronics 2025）。

---

## 5. IBIS-AMI联合仿真方法

### 5.1 IBIS-AMI模型框架

IBIS-AMI（Algorithmic Modeling Interface）是高速SerDes链路仿真的行业标准（来源：Signal Integrity Journal 2023, Latitude Design Systems 2023）。模型由三部分组成：

- **.ibs文件**：模拟缓冲器模型（I-V曲线、V-T曲线、封装寄生参数）
- **.ami文件**：参数配置文件（纯文本格式）
- **.dll/.so文件**：算法模型可执行代码（AMI_Init/AMI_GetWave）

### 5.2 包含TSV的3D-IC通道仿真流程

**完整仿真流程**（来源：SemiWiki 2013, Synopsys HSPICE, Keysight ADS）：

```
┌──────────────────────────────────────────────────────────────────┐
│ Step 1: TSV电磁建模                                                │
│   HFSS/CST → TSV S参数 (.sNp文件)                                 │
├──────────────────────────────────────────────────────────────────┤
│ Step 2: 通道级联                                                   │
│   Tx Package S参数 + TSV S参数 + Interposer S参数 + Rx Package S参数│
│   → 整体通道的Touchstone S参数文件                                 │
├──────────────────────────────────────────────────────────────────┤
│ Step 3: 模拟通道表征                                               │
│   EDA工具将S参数转换为时域冲激响应 hAC(t)                          │
│   需确保因果性和无源性（Causality & Passivity）                    │
├──────────────────────────────────────────────────────────────────┤
│ Step 4: IBIS-AMI仿真                                              │
│   ┌─────────────┐    ┌──────────┐    ┌─────────────┐             │
│   │Tx AMI_Init() │───▶│ hAC(t)   │───▶│Rx AMI_Init()│             │
│   │  FFE/预加重   │    │ 通道卷积  │    │ CTLE+DFE    │             │
│   └─────────────┘    └──────────┘    └─────────────┘             │
├──────────────────────────────────────────────────────────────────┤
│ Step 5: 性能分析                                                   │
│   → 眼图（Eye Diagram）: Eye Height, Eye Width                    │
│   → BER轮廓（Bathtub Curve）                                      │
│   → COM（Channel Operating Margin）                                │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 统计仿真 vs 时域仿真

| 特性 | 统计仿真（StatEye） | 时域仿真（Bit-by-Bit） |
|------|---------------------|------------------------|
| 速度 | 快（秒级） | 慢（分钟-小时级） |
| BER精度 | 可达1E-16 | 受限于仿真比特数 |
| 适用 | 线性时不变（LTI）通道 | 非线性/时变均衡器 |
| 函数 | AMI_Init() | AMI_GetWave() |
| 典型工具 | ADS Channel Simulator | HSPICE, Spectre |

### 5.4 TSV引入的关键仿真挑战

1. **S参数质量**：TSV的宽带S参数需确保因果性，否则AMI仿真会发散
2. **MOS电容效应**：TSV的非线性MOS电容在统计仿真中难以直接建模，需要线性化近似
3. **多端口耦合**：TSV阵列的串扰需要在AMI仿真中通过多端口S参数体现
4. **均衡器适配**：FFE tap数、CTLE peaking增益、DFE tap数需根据TSV通道特性优化

### 5.5 推荐工具链

| 工具 | 用途 |
|------|------|
| **ANSYS HFSS/CST** | TSV电磁建模，提取S参数 |
| **Keysight ADS** | 通道级联，IBIS-AMI仿真，COM计算 |
| **Synopsys HSPICE** | 包含TSV SPICE模型的时域仿真 |
| **MathWorks MATLAB** | COM计算，自定义均衡器算法开发 |
| **Cadence Sigrity** | 封装/PCB级SI/PI协同分析 |

---

## 6. 56Gbps PAM4信号完整性评估标准

### 6.1 PAM4基础

PAM4（4-Level Pulse Amplitude Modulation）使用4个电压电平传输2比特/符号，符号率是NRZ的一半（来源：Keysight, Tektronix Application Notes 2022）：

- 56Gbps PAM4 → 28Gbaud → Nyquist频率 = 14GHz
- 相比28Gbps NRZ，PAM4在相同带宽下传输2倍数据率
- 代价：信噪比（SNR）损失约9.5dB（3个眼，每个眼1/3摆幅）

### 6.2 关键评估指标

**眼图参数**（来源：Tektronix PAM4 App Note 51W-61416-0, Keysight N1930xB）：

| 指标 | 定义 | 56Gbps PAM4典型要求 |
|------|------|---------------------|
| **EH6 (Eye Height)** | SER=1E-6时的眼高 | > 30mV（取决于V_swing） |
| **EW6 (Eye Width)** | SER=1E-6时的眼宽 | > 0.5 UI (Unit Interval) |
| **RLM (Level Separation Mismatch Ratio)** | 电平间距均匀性 | > 0.9（IEEE 802.3ck要求） |
| **ESMW (Eye Symmetry Mask Width)** | 三眼水平对称性 | 通过掩模测试 |

**RLM计算公式**：
```
RLM = 3 × min(ES1, ES2, ES3) / (ES1 + ES2 + ES3)
```
其中ES1、ES2、ES3为三个眼的有效电平间距。

### 6.3 BER要求

**预FEC BER**（来源：IEEE 802.3ck, OIF CEI-56G）：

| 标准 | 预FEC BER | 后FEC FLR |
|------|-----------|-----------|
| IEEE 802.3ck (100G-PAM4) | ≤ 2.4E-4 | ≤ 1.7E-12 |
| OIF CEI-56G-PAM4 | ≤ 1E-6 (LR) | ≤ 1E-15 |
| 400GBASE-DR4 | ≤ 2.4E-4 | ≤ 1.7E-12 |

FEC（Forward Error Correction）使用RS(544,514) Reed-Solomon编码，可纠正最高15个符号错误。

### 6.4 通道插入损耗要求

**频域损耗预算**（来源：IEEE 802.3ck, Signal Integrity Journal 2022）：

| 频率 | 典型插入损耗限制 |
|------|------------------|
| 14GHz (Nyquist/2) | < 10dB |
| 28GHz (Nyquist for 100G) | < 20dB |
| 56GHz | < 35dB（含封装） |

**回波损耗要求**：< -10dB @ 28GHz（来源：Altium 224G PAM4 Channel Design Guide）

### 6.5 COM（Channel Operating Margin）

COM是IEEE 802.3标准中定义的通道质量综合指标（来源：IEEE 802.3ck, MathWorks 2023）：

- COM ≥ 3dB：通道合格
- COM计算考虑：插入损耗、回波损耗、串扰、抖动、均衡器能力
- 802.3ck COM包含DFE浮动tap位置和幅值确定

**COM计算包含的关键参数**：
1. 通道比特率（106.25Gbps用于802.3ck）
2. 插入损耗IL(f)
3. 回波损耗RL(f)
4. 综合串扰（ICN、FEN、NEN）
5. Tx/Rx均衡器能力（FFE tap数、CTLE peaking、DFE tap数）
6. 封装串扰与反射

### 6.6 均衡器要求

对于56Gbps PAM4通道，均衡器是必不可少的（来源：Signal Integrity Journal, Keysight）：

| 均衡器类型 | 位置 | 典型配置 |
|-----------|------|---------|
| FFE（Feed-Forward Equalizer） | Tx | 3-5 taps，预加重 |
| CTLE（Continuous-Time Linear Equalizer） | Rx | 1-2级，peaking gain 6-12dB |
| DFE（Decision Feedback Equalizer） | Rx | 5-16 taps，自适应 |

### 6.7 针对TSV通道的SI评估特殊考虑

TSV引入的独特挑战（来源：IMAPS 2023, Georgia Tech）：
- MOS电容电压依赖导致时变阻抗
- TSV阵列串扰引起确定性抖动（DJ）
- 慢波效应改变群延迟，影响PAM4时序
- 多TSV通道间skew导致的符号间干扰

**推荐评估方法**：
1. 使用包含TSV完整S参数的通道模型进行COM评估
2. 在IBIS-AMI仿真中同时考虑TSV的频域（S参数）和时域（SPICE宏模型）行为
3. 对TSV阵列采用蒙特卡洛仿真，评估工艺偏差对SI的影响

---

## 7. 参考文献

1. Georgia Tech Epsilon Lab, "Electromagnetic Modeling of Non-uniform TSV Interconnections," IEEE EPEPS, 2012. [Link](https://epsilon.ece.gatech.edu/publications/2012/conference/Electromagnetic_Modeling_of_Non-uniform_Through-Silicon_Via_(TSV)_Interconnections.pdf)
2. Georgia Tech GTCAD, "High Frequency Characterization and Modeling of High Density TSV in 3D ICs," IEEE, 2011. [Link](https://gtcad.gatech.edu/www/papers/05981999.pdf)
3. J. Kim et al., "High-Frequency Scalable Electrical Model and Analysis of TSV," IEEE Trans. CPMT, 2012. [Link](https://www.jpier.org/ac_api/download.php?id=15021404)
4. Drexel University, "Electrical Modeling and Characterization of TSV," IEEE Trans. Electron Devices, 2009. [Link](https://faculty.coe.drexel.edu/isavidis/publications/journals/TED_09.pdf)
5. Tsinghua University, "Analytical Modeling and Analysis of TSVs in High-Speed 3D System Integration," J. Semiconductors, 2015. [Link](https://numbda.cs.tsinghua.edu.cn/papers/jsemi15.pdf)
6. Georgia Tech, "Coupling Analysis of TSV Arrays in Silicon Interposers for 3D Systems," IBM/ISQED, 2011. [Link](https://gtcad.gatech.edu/www/papers/isqed11a.pdf)
7. MDPI Micromachines, "TSV Modeling Considering Signal Integrity Issues," 2024. [Link](https://www.mdpi.com/2072-666X/15/9/1127)
8. IMAPS, "Redistribution Layers (RDLs) for 2.5D/3D IC Integration," 2015. [Link](https://imapsource.org/article/56514-redistribution-layers-rdls-for-2-5d-3d-ic-integration.pdf)
9. IMAPS, "3D Electromagnetic Modeling of TSVs and Interposers in Electronic Packaging," 2023. [Link](https://imapsource.org/article/57256-3d-electromagnetic-modeling-of-through-silicon-vias-and-interposers-in-electronic-packaging.pdf)
10. MDPI Electronics, "Design and Optimization of RDL on Silicon Interposer," 2025. [Link](https://www.mdpi.com/2079-9292/15/5/945)
11. SemiWiki, "Modeling TSV, IBIS-AMI and SerDes with HSPICE," 2013. [Link](https://semiwiki.com/eda/synopsys/2069-modeling-tsv-ibis-ami-and-serdes-with-hspice/)
12. Signal Integrity Journal, "IBIS-AMI Modeling and Correlation Methodology for ADC-Based SerDes Beyond 100Gb/s," 2023. [Link](https://www.signalintegrityjournal.com/articles/2695-ibis-ami-modeling-and-correlation-methodology-for-adc-based-serdes-beyond-100-gb-s)
13. Latitude Design Systems, "Fundamental Aspects of IBIS-AMI Modeling and Simulation," 2023. [Link](https://www.latitudeds.com/post/fundamental-aspects-of-ibis-ami-modeling-and-simulation)
14. IEEE 802.3ck, "Physical Layer Specifications for 100/200/400 Gb/s Electrical Interfaces," 2022. [Link](https://standards.ieee.org/ieee/802.3ck/7322/)
15. Tektronix, "PAM4 Signaling in High-Speed Serial Technology," App Note 55W-60273. [Link](https://download.tek.com/document/PAM4-Signaling-in-High-Speed-Serial-Technology_55W-60273.pdf)
16. Keysight, "PAM4: Pulse Amplitude Modulation Explained," 2023. [Link](https://www.keysight.com/blogs/en/inds/ai/pam4-pulse-amplitude-modulation-explained)
17. Signal Integrity Journal, "Moving from 28Gbps NRZ to 56Gbps PAM4," 2022. [Link](https://www.signalintegrityjournal.com/blogs/12-fundamentals/post/796-moving-from-28-gbps-nrz-to-56-gbps-pam-4---is-it-free-lunch)
18. NTHU, "De-embedding Method for TSV Characterization," EPEPS, 2011. [Link](https://www.ee.nthu.edu.tw/shhsu/conference%20papers/de-embedding%20method_EPEPS_2011.pdf)
19. KAIST, "Modeling and Analysis of Coupling between TSVs, Metal and RDL Interconnects," 2011. [Link](https://pure.kaist.ac.kr/en/publications/modeling-and-analysis-of-coupling-between-tsvs-metal-and-rdl-inte/)
20. MathWorks, "Channel Operating Margin (COM) for Serial Link," 2023. [Link](https://www.mathworks.com/help/signal-integrity/ug/channel-operating-margin-com.html)