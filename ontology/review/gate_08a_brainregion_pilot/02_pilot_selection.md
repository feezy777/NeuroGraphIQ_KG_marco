# Gate 8A — Pilot Selection（可复现）

## 1. Selection rule（确定性，非"挑好看"）

```
PILOT_GYRI = [SFG, IFG, STG, MTG, SPL, IPL, Cun, Ins, Hipp]
PILOT_SUBCORTICAL_EXTRA = [Str, Th]
```

规则：
- 对 PILOT_GYRI 中每个 gyrus：取 **每半球最小 idx** 的 band（各 1 条）→ 9×2 = 18。
- 对 PILOT_SUBCORTICAL_EXTRA：取 **左侧最小 idx** 的 band → 2。
- 总计 **20** parcels；按 band_id 排序保证确定性。

## 2. 覆盖矩阵

| 维度 | 覆盖 |
|---|---|
| left / right | 11 L / 9 R |
| cortical / subcortical | 16 cortical（SFG,IFG,STG,MTG,SPL,IPL,Cun,Ins）×2 + 4 subcortical（Hipp×2, Str_L, Th_L） |
| anatomical group | frontal / temporal / parietal / occipital / insular / subcortical |
| 命名形式 | 含缩写（SFG,IFG）、复合（MTG,IPL）、拉丁（Cun）、深部结构（Hipp,Str,Th） |

## 3. 20 条 pilot 明细（band_id / native_name）

```
1 SFG_L_7_1    2 SFG_R_7_1    29 IFG_L_6_1   30 IFG_R_6_1
69 STG_L_6_1   70 STG_R_6_1   81 MTG_L_4_1   82 MTG_R_4_1
125 SPL_L_5_1  126 SPL_R_5_1  135 IPL_L_6_1  136 IPL_R_6_1
163 Ins_L_6_1  164 Ins_R_6_1  189 Cun_L_5_1  190 Cun_R_5_1
215 Hipp_L_2_1 216 Hipp_R_2_1 219 Str_L_6_1  231 Th_L_8_1
```

## 4. 可复现性

importer `_select_pilot()` 每次从源文件计算同一 20 条；rerun 结果一致。
