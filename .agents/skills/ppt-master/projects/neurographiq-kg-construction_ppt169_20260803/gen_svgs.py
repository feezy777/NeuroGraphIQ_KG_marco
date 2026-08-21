"""Generate remaining SVG pages P06-P14 for NeuroGraphIQ KG V3 presentation."""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'svg_output')
os.makedirs(OUT, exist_ok=True)

HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-pptx-page-role="content"><defs><filter id="g"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>'
BG = '<g id="bg" data-pptx-bounds="0 0 1280 720" data-pptx-role="background"><rect width="1280" height="720" fill="#0D1117"/><line x1="0" y1="108" x2="1280" y2="108" stroke="#212D40" stroke-width="0.5"/><text x="80" y="700" font-family="Microsoft YaHei" font-size="14" fill="#586069">NeuroGraphIQ KG V3</text></g>'
FOOT = '</svg>'
T = '<rect x="40" y="120" width="4" height="48" fill="#58A6FF" filter="url(#g)"/>'
TITLE = lambda t: f'{T}<text x="60" y="155" font-family="Microsoft YaHei" font-weight="bold" font-size="40" fill="#FFFFFF">{t}</text>'

def card(x, y, w, h, title, lines, accent="#58A6FF"):
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="#161B22" stroke="#30363D" stroke-width="0.5"/>']
    s.append(f'<rect x="{x}" y="{y}" width="{w}" height="4" fill="{accent}"/>')
    s.append(f'<text x="{x+20}" y="{y+40}" font-family="Microsoft YaHei" font-weight="bold" font-size="22" fill="{accent}">{title}</text>')
    for i, line in enumerate(lines):
        s.append(f'<text x="{x+20}" y="{y+75+i*28}" font-family="Microsoft YaHei" font-size="17" fill="#C9D1D9">{line}</text>')
    return '\n'.join(s)

def metric(x, y, val, label):
    return f'<rect x="{x}" y="{y}" width="175" height="75" rx="2" fill="#1C2333"/><text x="{x+87}" y="{y+32}" text-anchor="middle" font-family="Consolas" font-weight="bold" font-size="26" fill="#58A6FF">{val}</text><text x="{x+87}" y="{y+55}" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#8B949E">{label}</text>'

pages = {}

# P06 - Rule Validation & Enhancement
pages['P06_rule_validation.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("规则校验与数据增强引擎")}
<text x="40" y="200" font-family="Microsoft YaHei" font-size="20" fill="#8B949E">12 条确定性校验规则（不依赖 LLM）| Quality Score 加权评分</text>
<g transform="translate(40, 218)">
<rect x="0" y="0" width="580" height="26" rx="2" fill="#161B22"/><text x="10" y="18" font-family="Microsoft YaHei" font-weight="bold" font-size="13" fill="#8B949E">类别</text><text x="150" y="18" font-family="Microsoft YaHei" font-weight="bold" font-size="13" fill="#8B949E">检查项</text><text x="410" y="18" font-family="Microsoft YaHei" font-weight="bold" font-size="13" fill="#8B949E">级别</text>
<rect x="0" y="28" width="580" height="24" rx="2" fill="#1C2333"/><text x="10" y="45" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">完整性</text><text x="150" y="45" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">必填字段非空</text><text x="410" y="45" font-family="Consolas" font-size="14" fill="#FF7B72">BLOCKER</text>
<rect x="0" y="54" width="580" height="24" rx="2" fill="#1C2333"/><text x="10" y="71" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">语义ID / 唯一性</text><text x="150" y="71" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">格式合法性 / 同图谱不重复</text><text x="410" y="71" font-family="Consolas" font-size="14" fill="#FF7B72">BLOCKER</text>
<rect x="0" y="80" width="580" height="24" rx="2" fill="#1C2333"/><text x="10" y="97" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">拓扑</text><text x="150" y="97" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">脑区间引用有效性</text><text x="410" y="97" font-family="Consolas" font-size="14" fill="#FF7B72">BLOCKER</text>
<rect x="0" y="106" width="580" height="24" rx="2" fill="#1C2333"/><text x="10" y="123" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">溯源 / 证据</text><text x="150" y="123" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">atlas/version/resource齐全 / evidence_text</text><text x="410" y="123" font-family="Consolas" font-size="14" fill="#FFA657">WARNING</text>
</g>
<text x="40" y="390" font-family="Microsoft YaHei" font-size="20" fill="#8B949E">Quality Score: 完整性30% + 溯源20% + 拓扑20% + 证据20% + 关联10% = 0-100</text>
<!-- Enhancement Engine -->
<text x="40" y="430" font-family="Microsoft YaHei" font-size="20" fill="#8B949E">数据增强引擎</text>
{card(40, 448, 555, 96, "Tier 1: 确定性自动修复", ["补充缺失字段 · 标准化名称 · 修复引用","不调 LLM — 零成本 · 确定性 · 即时反馈"], "#38A169")}
{card(620, 448, 555, 96, "Tier 2: LLM 辅助增强 (DeepSeek)", ["分析疑难问题 → 生成修复建议","人工 approve / reject — 始终保留人工决策权"], "#58A6FF")}
</g>{FOOT}'''

# P07 - LLM Extraction
pages['P07_llm_extraction.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("LLM 知识提取：双模型驱动的知识关系构建")}
<text x="40" y="200" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">双 LLM 架构: DeepSeek (v4-pro / V3 / R1) + Kimi (Moonshot) · Provider 抽象层 · API Key 前端不可见</text>
<!-- Extraction tree -->
<rect x="390" y="220" width="500" height="40" rx="2" fill="#1A365D"/><text x="640" y="246" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="18" fill="#FFFFFF">候选脑区实体 (Candidate Brain Regions)</text>
<!-- Level 1 -->
<rect x="100" y="285" width="310" height="36" rx="2" fill="#1C3A6E"/><text x="255" y="309" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#79C0FF">连接提取 (Connection)</text>
<rect x="485" y="285" width="310" height="36" rx="2" fill="#1C3A6E"/><text x="640" y="309" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#79C0FF">功能提取 (Function)</text>
<rect x="870" y="285" width="310" height="36" rx="2" fill="#1C3A6E"/><text x="1025" y="309" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#79C0FF">回路提取 (Circuit)</text>
<!-- Level 2 -->
<rect x="100" y="345" width="310" height="36" rx="2" fill="#204A90"/><text x="255" y="369" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#FFA657">投射功能提取 (Proj Function)</text>
<rect x="485" y="345" width="310" height="36" rx="2" fill="#204A90"/><text x="640" y="369" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#FFA657">回路功能提取 (Circ Function)</text>
<rect x="870" y="345" width="310" height="36" rx="2" fill="#204A90"/><text x="1025" y="369" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#FFA657">回路步骤提取 (Circ Step)</text>
<!-- Level 3 -->
<rect x="390" y="405" width="500" height="40" rx="2" fill="#38A169"/><text x="640" y="431" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="18" fill="#FFFFFF">三元组整合 (Triple Consolidation) — 确定性，不调 LLM</text>
<!-- Workflow features -->
<text x="40" y="485" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">复合工作流: Pack 机制(pairs_per_pack 可调) · Dry Run 预览 · Skip Existing · 暂停/取消/恢复</text>
<g filter="url(#g)"><text x="640" y="530" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="18" fill="#FFA657">全部在同粒度内操作 · 跨粒度需显式 Mapping 表 · LLM 输出只写 Mirror KG</text></g>
</g>{FOOT}'''

# P08 - Mirror KG Governance
pages['P08_mirror_kg.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("Mirror KG：预正式知识中转层")}
<text x="40" y="190" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">解决 LLM 多 run/多 pack 重叠提取 · 重跑版本差异 · 审核员重复数据困境</text>
{card(40, 215, 380, 190, "写入时去重合并", ["每种实体定义 Canonical Key","写入时自动匹配与合并","高置信度胜出 + 双溯源保留","已审核/已晋升/跨粒度永不自动合并"], "#58A6FF")}
{card(440, 215, 380, 190, "双模型盲审", ["DeepSeek + Kimi 独立审核","两模型互相不可见对方结果","consensus → 加速审核通道","conflict → 升级人工裁决"], "#FFA657")}
{card(820, 215, 380, 190, "回路-投射交叉验证", ["正向: 回路→步骤→投射","反向: 投射→回路","双向确定性比对(不调LLM)","bidirectionally_supported / conflict"], "#38A169")}
<text x="40" y="445" font-family="Microsoft YaHei" font-size="20" fill="#8B949E">Canonical Key 体系</text>
<g transform="translate(40, 460)">
<rect x="0" y="0" width="380" height="30" rx="2" fill="#161B22"/><text x="10" y="20" font-family="Microsoft YaHei" font-weight="bold" font-size="15" fill="#8B949E">实体</text><text x="160" y="20" font-family="Microsoft YaHei" font-weight="bold" font-size="15" fill="#8B949E">Canonical Key</text>
<rect x="0" y="32" width="380" height="26" rx="2" fill="#1C2333"/><text x="10" y="50" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">连接</text><text x="160" y="50" font-family="Consolas" font-size="13" fill="#58A6FF">(src, tgt, type, dir) 无向时排序</text>
<rect x="0" y="60" width="380" height="26" rx="2" fill="#1C2333"/><text x="10" y="78" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">回路</text><text x="160" y="78" font-family="Consolas" font-size="13" fill="#58A6FF">(name, atlas, granularity)</text>
<rect x="0" y="88" width="380" height="26" rx="2" fill="#1C2333"/><text x="10" y="106" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">回路步骤</text><text x="160" y="106" font-family="Consolas" font-size="13" fill="#58A6FF">(circuit_id, step_order)</text>
<rect x="400" y="0" width="380" height="30" rx="2" fill="#161B22"/><text x="410" y="20" font-family="Microsoft YaHei" font-weight="bold" font-size="15" fill="#8B949E">合并策略</text>
<rect x="400" y="32" width="380" height="82" rx="2" fill="#1C2333"/>
<text x="420" y="52" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">· 高置信度胜出 → 更新字段+双溯源</text>
<text x="420" y="74" font-family="Microsoft YaHei" font-size="14" fill="#C9D1D9">· 低/等置信度 → 跳过+追加run_id</text>
<text x="420" y="96" font-family="Microsoft YaHei" font-size="14" fill="#FFA657">· 已审核/已晋升/跨atlas → 永不合并</text>
</g>
</g>{FOOT}'''

# P09 - Validation Center
pages['P09_validation_center.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("校验中心：三道闸门")}
<text x="40" y="190" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">Mirror KG 数据必须通过三道独立闸门才能进入 Final KG</text>
<!-- Three gates -->
{card(40, 215, 370, 200, "闸门 1: 规则校验", ["12 条规则 · 确定性 · 无 LLM","","Blocker → Tier1 自动修复","         → Tier2 LLM 增强","Warning → 标记提醒审核员"], "#1A365D")}
{card(430, 215, 370, 200, "闸门 2: 大模型校验", ["DeepSeek + Kimi 双模型盲审","","consensus → 绿色通道加速","conflict → 升级 + 分歧标注","两模型互不可见结果"], "#3068B0")}
{card(820, 215, 370, 200, "闸门 3: 人工审核", ["领域专家终审 · 唯一终审权","","approve → 进入晋升队列","reject → 退回 + 原因记录","request_changes → 返回修改"], "#FFA657")}
<!-- Convergence -->
<rect x="230" y="445" width="820" height="50" rx="2" fill="#1A365D" filter="url(#g)"/>
<text x="640" y="476" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="22" fill="#FFFFFF">→ Final KG（三道全过，缺一不可）←</text>
<g filter="url(#g)"><text x="640" y="540" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#8B949E">设计原则：前两道自动化（规则 + LLM 校验）+ 最后一道人工终审 = 效率与质量的最佳平衡</text></g>
</g>{FOOT}'''

# P10 - Promotion & Final KG
pages['P10_promotion_final_kg.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("晋升与 Final KG：唯一事实库")}
<text x="40" y="190" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">Mirror KG (审核通过) → Promotion 服务 → Final KG（8 表一一映射 · 强确认不可逆）</text>
<!-- Triple model -->
<rect x="40" y="215" width="1180" height="55" rx="2" fill="#1A365D"/><text x="630" y="240" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="20" fill="#FFFFFF">第一层: 实体层 (Nodes) — BrainRegion · Function · Circuit · Step · Projection</text><text x="630" y="260" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" fill="#79C0FF">AAL3/Macro96 脑区 · 功能标注 · 回路 · 步骤 · 投射/连接</text>
<rect x="40" y="285" width="1180" height="75" rx="2" fill="#1C3A6E"/>
<text x="630" y="310" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="20" fill="#FFFFFF">第二层: 关系层 (Predicates) — 12 种标准谓词</text>
<text x="630" y="335" text-anchor="middle" font-family="Consolas" font-size="15" fill="#58A6FF">structurally_connects_to  |  functionally_connects_to  |  projects_to  |  has_function</text>
<text x="630" y="353" text-anchor="middle" font-family="Consolas" font-size="15" fill="#79C0FF">has_projection_function  |  has_circuit_function  |  has_step  |  involves_region  |  contains_projection</text>
<rect x="40" y="375" width="1180" height="55" rx="2" fill="#204A90"/>
<text x="630" y="400" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="20" fill="#FFFFFF">第三层: 统一查询层 — final_kg_triples (subject, predicate, object) · 确定性 Triple Consolidation</text>
<text x="630" y="420" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" fill="#79C0FF">不调 LLM · CONNECTION_TO_PREDICATE 确定性映射 · 晋升后自动触发</text>
<!-- Granularity -->
<text x="40" y="470" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">五层粒度隔离: </text>
<g transform="translate(260, 455)">
<rect x="0" y="5" width="150" height="28" rx="2" fill="#1A365D"/><text x="75" y="24" text-anchor="middle" font-family="Consolas" font-size="13" fill="#58A6FF">macro_clinical</text>
<rect x="160" y="5" width="140" height="28" rx="2" fill="#1C2333"/><text x="230" y="24" text-anchor="middle" font-family="Consolas" font-size="13" fill="#586069">meso_anatomical</text>
<rect x="310" y="5" width="140" height="28" rx="2" fill="#1C2333"/><text x="380" y="24" text-anchor="middle" font-family="Consolas" font-size="13" fill="#586069">sub_connectivity</text>
<rect x="460" y="5" width="120" height="28" rx="2" fill="#1C2333"/><text x="520" y="24" text-anchor="middle" font-family="Consolas" font-size="13" fill="#586069">fine_cyto</text>
<rect x="590" y="5" width="140" height="28" rx="2" fill="#1C2333"/><text x="660" y="24" text-anchor="middle" font-family="Consolas" font-size="13" fill="#586069">molecular_attr</text>
</g>
<text x="40" y="520" font-family="Microsoft YaHei" font-size="16" fill="#FFA657">跨粒度关系: 显式 Mapping (exact_match / part_of / overlaps) · 禁止名称相似度自动合并</text>
</g>{FOOT}'''

# P11 - Consumption & Provenance
pages['P11_consumption_provenance.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("知识消费与全链路溯源")}
<text x="40" y="185" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">知识消费面</text>
{card(40, 200, 270, 120, "图谱探索", ["D3 力导向图可视化","节点展开/收起","按类型着色"], "#58A6FF")}
{card(330, 200, 270, 120, "症状查询", ["自然语言症状输入","标准化功能/回路匹配","→ 图谱结果+临床报告"], "#79C0FF")}
{card(620, 200, 270, 120, "数据中心", ["Raw→Candidate→Mirror","→Final 四面板浏览","字段补全 + 批量操作"], "#58A6FF")}
{card(910, 200, 270, 120, "知识导出", ["JSONL + CSV","+ Neo4j 兼容格式","离线确定性导出"], "#79C0FF")}
<!-- Provenance chain -->
<text x="40" y="365" font-family="Microsoft YaHei" font-size="18" fill="#8B949E">全链路溯源 — 任何 Final KG 事实 → 7 步回溯 → 原始出处</text>
<g transform="translate(40, 385)">
<rect x="0" y="0" width="130" height="36" rx="2" fill="#1A365D"/><text x="65" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#FFFFFF">Final KG 事实</text>
<text x="140" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="160" y="0" width="120" height="36" rx="2" fill="#1C3A6E"/><text x="220" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#79C0FF">promotion</text>
<text x="290" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="310" y="0" width="120" height="36" rx="2" fill="#204A90"/><text x="370" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#FFA657">review</text>
<text x="440" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="460" y="0" width="130" height="36" rx="2" fill="#2858A0"/><text x="525" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#C9D1D9">rule_validation</text>
<text x="600" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="620" y="0" width="140" height="36" rx="2" fill="#3068B0"/><text x="690" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="#58A6FF">llm_item(raw)</text>
<text x="770" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="790" y="0" width="130" height="36" rx="2" fill="#3878C0"/><text x="855" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#79C0FF">llm_run</text>
<text x="930" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="950" y="0" width="120" height="36" rx="2" fill="#1A365D"/><text x="1010" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="13" fill="#FFFFFF">candidate_pool</text>
<text x="1080" y="24" font-family="Consolas" font-size="18" fill="#30363D">→</text>
<rect x="1100" y="0" width="100" height="36" rx="2" fill="#1C3A6E"/><text x="1150" y="23" text-anchor="middle" font-family="Microsoft YaHei" font-size="12" fill="#79C0FF">import_batch</text>
</g>
<text x="640" y="450" text-anchor="middle" font-family="Microsoft YaHei" font-size="14" fill="#586069">import_batch → resource (原始脑图谱资源) — 全链路不可篡改，provenance 是晋升的硬性前提</text>
<g filter="url(#g)"><text x="640" y="500" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="20" fill="#58A6FF">任何 Final KG 事实 → 7 步回溯 → 原始脑图谱资源出处</text></g>
</g>{FOOT}'''

# P12 - Innovation Summary
pages['P12_innovation.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("核心创新点")}
{card(40, 190, 370, 160, "1. 分层漏斗治理", ["6 阶段流水线","候选→校验→LLM→Mirror","→Review→Final","每层明确写边界"], "#1A365D")}
{card(430, 190, 370, 160, "2. Mirror KG 中转层", ["写入时去重合并","Canonical Key 体系","双溯源保留","永不自动合并已审核数据"], "#3068B0")}
{card(820, 190, 370, 160, "3. 双模型盲审", ["DeepSeek + Kimi","独立审核同一数据","互不可见结果","冲突人工裁决"], "#3878C0")}
{card(40, 375, 370, 160, "4. 数据增强引擎", ["Tier 1 确定性修复(零成本)","Tier 2 LLM 增强","Quality Score 0-100","自动评分与分层修复"], "#38A169")}
{card(430, 375, 370, 160, "5. 全链路溯源", ["7 步回溯到原始出处","所有 provenance 不可变","晋升硬性前提","证据层完整记录"], "#FFA657")}
{card(820, 375, 370, 160, "6. 五层粒度隔离", ["PostgreSQL schema 级","物理隔离","跨粒度显式 Mapping","禁止名称相似度合并"], "#FF7B72")}
</g>{FOOT}'''

# P13 - Status & Next Steps
pages['P13_status.svg'] = f'''{HEAD}{BG}<g id="c" data-pptx-bounds="40 120 1200 560">
{TITLE("当前状态与下一步规划")}
<text x="40" y="185" font-family="Microsoft YaHei" font-weight="bold" font-size="24" fill="#38A169">已完成</text>
<g transform="translate(40, 198)">
<rect x="0" y="0" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="19" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">端到端流水线 (Resource → Final KG) 闭环</text>
<rect x="0" y="30" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="49" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">7 种 LLM 提取能力 + 复合工作流编排</text>
<rect x="0" y="60" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="79" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">12 规则校验 + 数据增强引擎 (Tier 1 + Tier 2)</text>
<rect x="0" y="90" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="109" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">双模型盲审 + 交叉验证</text>
<rect x="0" y="120" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="139" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">Mirror → Final 晋升 + Triple Consolidation</text>
<rect x="0" y="150" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="169" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">写入时去重合并 (6 类实体全覆盖)</text>
<rect x="0" y="180" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="199" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">14 页前端工作台 + Graph Explorer + 症状查询</text>
<rect x="0" y="210" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="229" font-family="Microsoft YaHei" font-size="15" fill="#C9D1D9">1,173 测试函数 · 59 数据库迁移 · 全链路 audit</text>
</g>
<rect x="615" y="170" width="2" height="280" fill="#30363D"/>
<text x="640" y="185" font-family="Microsoft YaHei" font-weight="bold" font-size="24" fill="#FFA657">规划中</text>
<g transform="translate(640, 198)">
<rect x="0" y="0" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="19" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">接入更多粒度数据</text>
<rect x="0" y="30" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="49" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">图数据库同步 (Neo4j 可选路径)</text>
<rect x="0" y="60" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="79" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">跨粒度映射关系自动发现</text>
<rect x="0" y="90" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="109" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">Graph Explorer 交互增强 (ReactFlow)</text>
<rect x="0" y="120" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="139" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">DashBoard 关键指标看板</text>
<rect x="0" y="150" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="169" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">批量字段补全进度可视化</text>
<rect x="0" y="180" width="555" height="28" rx="2" fill="#1C2333"/><text x="10" y="199" font-family="Microsoft YaHei" font-size="15" fill="#8B949E">知识图谱版本管理与差异对比</text>
</g>
<!-- Metrics -->
<g transform="translate(40, 515)">
{metric(0, 0, "42+88", "API 路由 · 服务")}
{metric(190, 0, "14", "前端页面")}
{metric(380, 0, "5+59", "Schema · 迁移")}
{metric(570, 0, "1,173", "测试函数")}
{metric(760, 0, "7", "知识层")}
{metric(950, 0, "2", "LLM 模型")}
</g>
</g>{FOOT}'''

# P14 - Thank You
pages['P14_thank_you.svg'] = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" data-pptx-page-role="ending">
  <defs>
    <filter id="gs"><feGaussianBlur stdDeviation="6" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    <radialGradient id="bgGrad" cx="50%" cy="40%" r="70%"><stop offset="0%" stop-color="#161B22"/><stop offset="100%" stop-color="#0D1117"/></radialGradient>
  </defs>
  <g id="bg" data-pptx-bounds="0 0 1280 720" data-pptx-role="background"><rect width="1280" height="720" fill="url(#bgGrad)"/></g>
  <g id="dec" data-pptx-bounds="0 0 1280 720" data-pptx-role="decoration">
    <g opacity="0.06">
      <circle cx="200" cy="200" r="3" fill="#58A6FF" stroke="none"/><circle cx="400" cy="150" r="2" fill="#58A6FF" stroke="none"/>
      <circle cx="600" cy="250" r="3" fill="#58A6FF" stroke="none"/><circle cx="880" cy="180" r="2" fill="#79C0FF" stroke="none"/>
      <circle cx="1050" cy="220" r="3" fill="#79C0FF" stroke="none"/>
      <circle cx="300" cy="500" r="2" fill="#58A6FF" stroke="none"/><circle cx="500" cy="550" r="3" fill="#79C0FF" stroke="none"/>
      <circle cx="750" cy="520" r="2" fill="#58A6FF" stroke="none"/><circle cx="950" cy="580" r="3" fill="#79C0FF" stroke="none"/>
    </g>
  </g>
  <g id="c" data-pptx-bounds="0 0 1280 720">
    <text x="640" y="300" text-anchor="middle" font-family="Microsoft YaHei" font-weight="bold" font-size="64" fill="#FFFFFF" filter="url(#gs)">感谢关注</text>
    <text x="640" y="380" text-anchor="middle" font-family="Microsoft YaHei" font-size="32" fill="#79C0FF">欢迎提问与交流</text>
    <line x1="500" y1="430" x2="780" y2="430" stroke="#58A6FF" stroke-width="1.5" opacity="0.5"/>
    <text x="640" y="490" text-anchor="middle" font-family="Microsoft YaHei" font-size="20" fill="#8B949E">NeuroGraphIQ KG V3 — 多粒度脑区知识图谱</text>
    <text x="640" y="600" text-anchor="middle" font-family="Microsoft YaHei" font-size="16" fill="#586069">2026 年 8 月</text>
    <line x1="80" y1="670" x2="1200" y2="670" stroke="#212D40" stroke-width="0.5"/>
  </g>
</svg>'''

# Write all pages
for fname, content in pages.items():
    path = os.path.join(OUT, fname)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

existing = sorted(os.listdir(OUT))
print(f"Generated {len(pages)} pages")
print(f"Total SVG files: {len(existing)}")
for f in existing:
    print(f"  {f}")
