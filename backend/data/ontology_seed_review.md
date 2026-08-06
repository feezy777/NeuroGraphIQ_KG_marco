# 本体种子候选：canonical 词表 + 同义词合并建议

> 生成时间：2026-08-06T03:17:15.166232+00:00（纯规则，无 LLM）

## 统计

- 去重术语总数：**9126**
- 聚类后 canonical 候选：**7761**
- 同义词簇（需要合并的变体组）：**1140**
- 覆盖记录数：**114110**

## 同义词合并建议（按覆盖量排序，Top 60）

| canonical（建议保留） | 变体（建议归入同义词） | 覆盖量 |
|---|---|---|
| `visual processing` | `visual processing`(2863) | 7401 |
| `somatosensory processing` | `somatosensory processing`(2243) | 5559 |
| `motor coordination` | `motor coordination`(793) | 3404 |
| `auditory processing` | `auditory processing`(1334) | 3218 |
| `olfactory processing` | `olfactory processing`(1141) | 3168 |
| `emotional processing` | `emotional processing`(542), `emotion_processing`(32), `emotion processing`(13) | 3147 |
| `unknown` | `unknown function`(76), `unknown functional association`(62) | 2927 |
| `memory encoding` | `memory encoding`(554) | 2588 |
| `cognitive control` | `cognitive control`(561) | 1912 |
| `motor planning` | `motor planning`(357) | 1706 |
| `memory processing` | `memory processing`(448) | 1622 |
| `multisensory integration` | `multisensory integration`(523) | 1545 |
| `cerebellar processing` | `cerebellar processing`(247) | 1297 |
| `visual signal transmission` | `visual signal transmission`(24) | 1296 |
| `sensory relay` | `sensory relay`(85) | 1252 |
| `spatial navigation` | `spatial navigation`(359) | 1194 |
| `spatial memory` | `spatial memory`(375) | 1132 |
| `sensory integration` | `sensory integration`(358) | 1067 |
| `autonomic regulation` | `autonomic regulation`(192) | 985 |
| `emotional regulation` | `emotional regulation`(200), `emotion regulation`(149), `emotion_regulation`(59) | 888 |
| `memory consolidation` | `memory consolidation`(196) | 823 |
| `spatial processing` | `spatial processing`(125) | 821 |
| `somatosensory relay` | `somatosensory relay`(78) | 784 |
| `sensory processing` | `sensory processing`(237) | 776 |
| `sensory transmission` | `sensory transmission`(132) | 759 |
| `somatosensory transmission` | `somatosensory transmission`(171) | 730 |
| `gustatory processing` | `gustatory processing`(246) | 687 |
| `reward processing` | `reward processing`(142) | 597 |
| `visual relay` | `visual relay`(31) | 582 |
| `somatosensory signal transmission` | `somatosensory signal transmission`(11) | 550 |
| `motor learning` | `motor learning`(99) | 548 |
| `memory modulation` | `memory modulation`(245) | 537 |
| `executive control` | `executive control`(195) | 505 |
| `stress response` | `stress response`(101) | 481 |
| `sensorimotor integration` | `sensorimotor_integration`(225) | 471 |
| `olfactory relay` | `olfactory relay`(17) | 471 |
| `memory retrieval` | `memory retrieval`(75) | 458 |
| `multimodal integration` | `multimodal integration`(73) | 448 |
| `memory integration` | `memory integration`(151) | 442 |
| `motor command` | `motor command`(29) | 396 |
| `somatosensory integration` | `somatosensory integration`(178) | 387 |
| `limbic integration` | `limbic integration`(36) | 385 |
| `visual transmission` | `visual transmission`(68) | 375 |
| `visceral sensation` | `visceral sensation`(70) | 361 |
| `emotional modulation` | `emotional modulation`(58) | 357 |
| `auditory relay` | `auditory relay`(40) | 357 |
| `visual signal relay` | `visual signal relay`(5) | 339 |
| `motor control` | `motor control`(50) | 310 |
| `neuroendocrine regulation` | `neuroendocrine regulation`(131) | 307 |
| `hippocampal output` | `hippocampal output`(53) | 290 |
| `cross-modal sensory integration` | `cross_modal_sensory_integration`(33), `cross-modal_sensory_integration`(11) | 287 |
| `auditory signal transmission` | `auditory signal transmission`(6) | 280 |
| `visual integration` | `visual integration`(103) | 270 |
| `emotional response` | `emotional response`(20) | 263 |
| `memory relay` | `memory relay`(23) | 261 |
| `spatial attention` | `spatial attention`(52) | 254 |
| `cross modal integration` | `cross-modal integration`(56) | 254 |
| `pattern separation` | `pattern separation`(65) | 248 |
| `visceral processing` | `visceral processing`(62) | 240 |
| `cerebellar modulation` | `cerebellar modulation`(62) | 234 |

## 高频 canonical 候选（Top 100）

| 排名 | canonical | 覆盖量 | 来源 |
|---|---|---|---|
| 1 | `visual processing` | 4538 | circuit_function, region_function |
| 2 | `somatosensory processing` | 3316 | circuit_function, region_function |
| 3 | `unknown` | 2789 | circuit_function, projection_function, region_function |
| 4 | `motor coordination` | 2611 | circuit_function, region_function |
| 5 | `emotional processing` | 2560 | circuit_function |
| 6 | `memory encoding` | 2034 | circuit_function, region_function |
| 7 | `olfactory processing` | 2027 | circuit_function |
| 8 | `auditory processing` | 1884 | circuit_function, region_function |
| 9 | `cognitive control` | 1351 | circuit_function, region_function |
| 10 | `motor planning` | 1349 | circuit_function |
| 11 | `visual signal transmission` | 1272 | circuit_function |
| 12 | `memory processing` | 1174 | circuit_function |
| 13 | `sensory relay` | 1167 | circuit_function, region_function |
| 14 | `interoception` | 1153 | circuit_function, projection_function, region_function |
| 15 | `integration` | 1147 | circuit_function |
| 16 | `cerebellar processing` | 1050 | circuit_function |
| 17 | `multisensory integration` | 1022 | circuit_function |
| 18 | `relay` | 974 | circuit_function |
| 19 | `visual sensory processing` | 961 | circuit_function |
| 20 | `spatial navigation` | 835 | circuit_function |
| 21 | `autonomic regulation` | 793 | circuit_function, region_function |
| 22 | `spatial memory` | 757 | circuit_function |
| 23 | `sensory integration` | 709 | circuit_function |
| 24 | `somatosensory relay` | 706 | circuit_function |
| 25 | `spatial processing` | 696 | circuit_function |
| 26 | `memory consolidation` | 627 | circuit_function, region_function |
| 27 | `sensory transmission` | 627 | circuit_function |
| 28 | `somatosensory transmission` | 559 | circuit_function |
| 29 | `visual relay` | 551 | circuit_function |
| 30 | `sensory processing` | 539 | circuit_function |
| 31 | `somatosensory signal transmission` | 539 | circuit_function |
| 32 | `emotional regulation` | 480 | circuit_function |
| 33 | `reward processing` | 455 | circuit_function, region_function |
| 34 | `olfactory relay` | 454 | circuit_function |
| 35 | `motor learning` | 449 | circuit_function, region_function |
| 36 | `gustatory processing` | 441 | circuit_function |
| 37 | `memory retrieval` | 383 | circuit_function |
| 38 | `stress response` | 380 | circuit_function |
| 39 | `multimodal integration` | 375 | circuit_function |
| 40 | `motor command` | 367 | circuit_function |
| 41 | `limbic integration` | 349 | circuit_function |
| 42 | `visual signal relay` | 334 | circuit_function |
| 43 | `auditory relay` | 317 | circuit_function |
| 44 | `executive control` | 310 | circuit_function |
| 45 | `visual transmission` | 307 | circuit_function |
| 46 | `emotional modulation` | 299 | circuit_function |
| 47 | `memory modulation` | 292 | circuit_function |
| 48 | `visceral sensation` | 291 | circuit_function |
| 49 | `memory integration` | 291 | circuit_function |
| 50 | `auditory signal transmission` | 274 | circuit_function |
| 51 | `motor control` | 260 | circuit_function, region_function |
| 52 | `sensorimotor integration` | 246 | circuit_function, projection_function |
| 53 | `cross-modal sensory integration` | 243 | circuit_function, projection_function |
| 54 | `emotional response` | 243 | circuit_function |
| 55 | `memory relay` | 238 | circuit_function |
| 56 | `hippocampal output` | 237 | circuit_function |
| 57 | `visual sensory transmission` | 217 | circuit_function |
| 58 | `somatosensory integration` | 209 | circuit_function |
| 59 | `sensory projection` | 204 | circuit_function |
| 60 | `spatial attention` | 202 | circuit_function, region_function |
| 61 | `olfactory signal transmission` | 200 | circuit_function |
| 62 | `hippocampal processing` | 199 | circuit_function |
| 63 | `cross modal integration` | 198 | circuit_function |
| 64 | `visual input` | 197 | circuit_function |
| 65 | `motor output` | 194 | circuit_function |
| 66 | `somatosensory projection` | 189 | circuit_function |
| 67 | `pattern separation` | 183 | circuit_function |
| 68 | `visceral processing` | 178 | circuit_function |
| 69 | `neuroendocrine regulation` | 176 | circuit_function |
| 70 | `somatosensory input` | 175 | circuit_function |
| 71 | `executive function` | 174 | circuit_function |
| 72 | `cerebellar modulation` | 172 | circuit_function |
| 73 | `motor execution` | 169 | circuit_function |
| 74 | `olfactory sensory processing` | 168 | circuit_function |
| 75 | `cerebellar output` | 168 | circuit_function |
| 76 | `visual integration` | 167 | circuit_function |
| 77 | `motor signal transmission` | 166 | circuit_function |
| 78 | `visuomotor coordination` | 164 | circuit_function, projection_function |
| 79 | `auditory transmission` | 164 | circuit_function |
| 80 | `motor relay` | 161 | circuit_function |
| 81 | `interoceptive processing` | 158 | circuit_function |
| 82 | `memory signal transmission` | 158 | circuit_function |
| 83 | `memory formation` | 148 | circuit_function |
| 84 | `decision making` | 148 | circuit_function |
| 85 | `salience processing` | 143 | circuit_function |
| 86 | `hippocampal input` | 142 | circuit_function |
| 87 | `visual projection` | 141 | circuit_function |
| 88 | `visual association` | 137 | circuit_function |
| 89 | `emotional signal transmission` | 133 | circuit_function |
| 90 | `cognitive processing` | 132 | circuit_function |
| 91 | `olfactory integration` | 131 | circuit_function |
| 92 | `spatial memory processing` | 131 | circuit_function |
| 93 | `sensory input` | 131 | circuit_function |
| 94 | `emotional integration` | 127 | circuit_function |
| 95 | `visceral sensory processing` | 125 | circuit_function |
| 96 | `limbic relay` | 124 | circuit_function |
| 97 | `olfactory transmission` | 124 | circuit_function |
| 98 | `object recognition` | 123 | circuit_function |
| 99 | `cortical output` | 118 | circuit_function |
| 100 | `association` | 118 | circuit_function |