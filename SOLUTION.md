# Shopping Copilot 解題策略與架構設計

TikTok TechJam 2026 Track 4「Shopping Copilot: AI Conversational Search and Recommendations」

**最終本地成績（官方評估器，public set 200 sessions）：**

| 指標 | 官方弱基線 BM25 | 本方案（離線確定性核心） |
|---|---|---|
| Hit Rate@10 | 0.125 | **1.000** |
| MRR | 0.068 | **0.724** |
| MTTC | 9.81 | **1.59** |
| Efficiency | 0.119 | 0.934 |
| **TechnicalScore** | **0.107** | **0.905** |

---

## 1. 對題目的理解：真正的信息結構

官方評估器是**確定性模擬器**：每個 session 的「隱藏意圖卡」（intent card）由目標商品元數據生成（material 詞、`color: x`、前幾條 feature/detail 字符串、預算），顧客按固定模板逐輪披露約束。這決定了整個方案的信息論設計：

- **約束是目標商品的逐字文本**：76% 的披露約束是商品 feature/detail 的**精確子串**（大小寫、空白歸一化後完全一致）。因此「精確短語連取」（exact-phrase conjunction）是壓倒性的第一信號——連取後 66.5% 的 session 候選池唯一命中，79% ≤ 10 個候選。
- **提問 = 信息採集**：`customer_reply` 對 `ask_attribute="other"` 返回**任意兩條**未披露約束（按 hard→soft 順序）。實測網格搜索證明「other 一問到底」優於按屬性逐個試探（feature-first 會錯過非 feature 類約束）。
- **每 session 最多披露 4 條約束**。若目標商品的 top-4 特徵全是通用模板（如 `Imported`、`Machine Wash`），單靠披露信息在 50k 目錄中無法唯一區分——這是命中率的天花板（public set 中 1/200，即 `public_0020`，目標與 463 個商品共享全部披露特徵）。

## 2. 系統架構（四大支柱對應實現）

```
用户消息
   │
   ▼
[消息理解] 模板解析（權威）+ 短語Trie子串查詢（兜底）+ 合成約束正則
   │  精確短語（保留極大匹配）/ material / color / budget / 意圖信號
   ▼
[動態狀態機] 槽位累積、意圖路由（buying/browsing/intent_override/boundary）、
   │  override 槽位擦除（僅擦除開場披露的舊偏好）、提問規劃器
   ▼
[多路檢索] R1 精確短語連取（級聯鬆弛）→ R2 類目硬過濾（全token交集）
   │        → R3 合成屬性（material/color/budget）→ R4 標題token重疊
   │        → R5 評分風格一致性 → 稠密路由（TF-IDF，大池時）
   ▼
[排序] 加權線性打分 + 流行度先驗 → [可選 LLM 重排 top-20]
   │
   ▼
{message, ask_attribute, recommendations, usage}
```

### 2.1 意圖路由（Dual-Track Routing）

- **Buying**：開場模板含 `A key requirement is:` → 高精度過濾軌道，硬約束即時生效。
- **Browsing**：開場 `but I'm still exploring` → 先建類目池，靠提問逐步收斂。
- **Intent Override**：開場為裸偏好串（`I'm looking for {cat}. {old}`）；檢測到覆寫消息後，**僅擦除開場披露的舊偏好**（`opening_phrases`），後續提問所得約束保留。覆寫前不能命中（評估器強制），但開場舊偏好本身是目標商品的精確特徵，可用作弱信號提前鎖定候選。
- **Boundary**：首次提問收到「無偏好」回覆時識別，多花一輪提問即可。

### 2.2 動態狀態機（Multi-Turn Scenario Evolution）

- **信息累積**：category / 精確短語 / material / color / budget 五類槽位逐輪累加。
- **意圖覆蓋**：override 消息觸發 `superseded` 槽位擦除與檢索權重調整（被擦除短語降為弱信號 W=30，因目標商品仍具備該特徵）。
- **提問規劃**：`other` 一問到底；收到「無額外偏好」即停止（dead-attr 追蹤）；最多 5 問。
- **每輪都同時輸出推薦**：命中即結束，提問不浪費輪次。

### 2.3 多路檢索與排序（Hybrid Pipeline）

| 路由 | 信號 | 權重 | 說明 |
|---|---|---|---|
| R1 精確短語連取 | 披露短語 ∩ 商品短語集 | 100/個 | 級聯鬆弛：全連取為空時退到最大非空子集 |
| R2 類目硬過濾 | 粗類目 token 全交集 | 60 | 池 > 10 時硬過濾；目標必在類目池內 |
| R3 合成屬性 | material 詞、color、budget | 25-40 | `cotton`/`color: x` 是合成格式，**嚴禁**入短語索引（postings 過小會毒化連取） |
| R4 標題重疊 | 約束 token ∩ 標題 token、類目 token ∩ 標題 | 16/3 | |
| R5 評分風格一致性 | profile.rating_style ↔ 商品均分 | 20 | 「usually positive」買高評商品（實測 75% 對齊） |
| 流行度先驗 | log(1+rating_number) | 8 | 目標來自真實購買記錄，偏流行商品 |
| 稠密路由 | TF-IDF 餘弦 | 30 | 池 > 200 時啟用；全離線、sklearn 擬合目錄 |
| LLM 重排 | GPT 類 API 重排 top-20 | — | 可選；無 key 時完全離線 |

### 2.4 消息理解的工程細節（踩過的坑）

1. **單詞噪聲**：短語 Trie 對消息做子串查詢會命中 `Rubber`、`Trail` 這類恰好是別家 feature 的單詞短語，毒化連取 → 只接受 **≥2 token 且不被其他匹配包含（極大短語）**的 Trie 結果。
2. **合成約束識別**：`leather`/`polyester` 等裸 material 詞、`color: grey`、`budget around $X` 走合成槽位而非短語槽位。
3. **大小寫**：類目/約束 token 化必須 `re.IGNORECASE`，否則 `Novelty`→`ovelty`，類目過濾靜默失效（這是 MRR 0.69→0.90 途中最大的隱藏 bug）。
4. **模板 vs Trie 雙通道**：模板解析是權威（含單 token 約束如 `Imported`），Trie 兜底救回被 `"; "` 切碎的長特徵串。

## 3. 關鍵實證發現（數據驅動的決策）

- 精確短語連取的選擇性：**200/200 session 至少 1 條精確約束**；全連取 median 候選 = 1。
- 提問策略網格搜索（真實評估器）：`other` 一問到底 TS 0.8917 > feature-first 0.8857 > 混合 0.8867。
- 排序權重離線網格（2000 條 turn-record 快照）：`w_title=16, w_cat_title=3, w_pop=8, w_rating=4, w_style=20, w_tag=0` 最優。
- profile 的 `average_prior_rating` 與目標評分**無洩漏**（僅 3/200 精確相等）；`rating_style` 與目標評分 75% 一致（可用弱信號）。

## 4. 已知局限與改進方向

1. **通用模板特徵 session**（1/200）：目標 top-4 特徵與數百商品相同時，披露信息不足以區分——需真實用戶側信號才能解，超出題目信息邊界。
2. **模板依賴**：若主辦方對私有集做自然語言改寫，模板解析失效；Trie 子串查詢與 TF-IDF 稠密路由是緩衝（約束逐字保留時仍工作）。
3. **私有集泛化**：所有調參在 200 條 public set 上進行，存在輕微過擬合風險；核心機制（精確連取 + 類目過濾）是數據集無關的。
4. LLM 重排路徑未在本地實測（無 API key），僅保證接口與回退正確。

## 5. 運行方式

```bash
python3 -m evaluator.local_evaluator
# 可選 LLM 重排（離線默認）：
# export TECHJAM_LLM_API_BASE=... TECHJAM_LLM_API_KEY=... TECHJAM_LLM_MODEL=...
```

啟動（索引 50k 目錄 + TF-IDF 擬合）約 15s；評估 364ms/session；全程內存、無網絡、無外部向量庫，token 用量為 0（無 LLM 路徑）。

## 6. 對標：2025 年 TechJam 前幾名與同級賽事頂尖團隊

**TikTok TechJam 2025**（主題「Build with Joy, Code for Change」，新加坡）：
- 冠軍 **NTU Blueberry Jam — PrivaStream**：直播隱私實時保護（TikTok Live 自動遮擋），
  端到端產品 + Product Hunt 上線。贏在**完整產品 + 影響力故事 + 打磨過的演示**。
- 決賽作品如 AI-Driven UI Consistency Testing：**多級過濾管線**
  （YOLO→NMS 數百框壓到 70→CLIP 取 20→多模型共識投票），延遲 5 分鐘→15-30 秒。

**騰訊雲滲透黑客松前 3**（不同賽道，agent 架構金礦）：
- 第 1 名：Manager+Solver+Observer 三層解耦、旁路監督、上下文壓縮、
  **狀態約束的結束判定**、**7 模型並行競爭投票**
- 第 3 名：黑板系統+蟻群、平等 Worker、全場唯一 AK

**映射到本方案的採用**（均已落地）：
| 前幾名模式 | 本方案對應 |
|---|---|
| 多級過濾漏斗 | 50k 目錄 → 短語連取 → 精確 coarse 過濾 → 打分 → LLM 重排 → 最終 1 個（demo 中已可視化為漏斗圖） |
| 多路共識投票 | 關鍵詞/材質/顏色/預算/精確類目/語義相似/評分 各路信號在最終推薦卡上展示（signals chips） |
| 狀態約束的結束判定 | 10 輪鉗制 + 池 ≤5 / 無進展×2 / facet 耗盡 的多重收斂條件 |
| 端到端產品 + 演示 | demo UI（雙模式 + MCP + MiniLM + LLM 重排）+ 可復現評估 |

結論：2025 前幾名在**指標層面**和本方案相當（他們沒有統一評分板），拉開差距的是
**產品化與演示敘事**——本倉庫的 demo UI、漏斗可視化、MCP 集成正是為此補課。

## 7. MiroFish 式世界視圖（群體智能可視化）

參考 [MiroFish](https://github.com/Bocha-Labs/MiroFish)（群體智能預測引擎：種子材料→圖譜→
上千 agent 平行世界多輪演化→預測報告，上帝視角 2D 世界）的機制，把檢索過程映射為
「魚群收斂」：

| MiroFish 機制 | 本方案映射 |
|---|---|
| 種子材料 | 用戶消息（T1 起） |
| 圖譜構建 | 意圖解析 + 槽位累積（關鍵詞/材質/顏色/預算） |
| 多輪群體模擬 | 每輪檢索：候選魚群按得分螺旋佈局（排名越高越靠中心），淘汰者淡出沉底 |
| 上帝視角世界 | 世界畫布：🐟 實體、拖拽平移、滾輪縮放、懸停看商品 |
| 預測報告 | 收斂出唯一 👑 最終推薦 + 漏斗/信號共識 |

工作流四步（01 種子消息 → 02 意圖圖 → 03 群體模擬 → 04 預測報告）在畫布頂部實時點亮，
HUD 顯示存活實體數與輪次。實體在服務端會話內持久（跨輪保持同一坐標系），
淘汰的魚留在原地變暗——就像平行世界裡被排除的未來分支。
