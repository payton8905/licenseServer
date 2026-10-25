# Keygen CE + 官方 Portal 本機 PoC

Windows Docker Desktop 可直接執行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\docker-start.ps1`，不需額外安裝 WSL 發行版、Python 或 Git。完整步驟見 [README 的 Windows Docker 一鍵啟動](README.md#windows-docker-一鍵啟動)。下列 `python3` 指令仍以 Linux 環境為準。

此目錄已拆為獨立 LicenseServer 專案。請先閱讀 [README.md](README.md)；下列產品整合指令需要預先設定 `SBOMSCAN_SOURCE_DIR`、`LICENSE_SERVER_DIR` 為絕對路徑。本文「產品根目錄」指 SBOMScan checkout，「本目錄」指 LicenseServer。

第一次操作請先看 **[圖文操作手冊](manual/操作手冊.md)**，或以瀏覽器開啟 **[可列印圖文版](manual/操作手冊.html)**。手冊包含管理端登入、核發與找回 License Key、客戶啟用、完全離線交付、續約、換機及問題排除。

授權狀態與功能限制的最新驗證請看 **[授權功能檢查報告](manual/授權檢查報告.md)**。`python3 ./audit.py` 會使用隔離資料庫與暫時 Keygen Product，重跑模式、模組、期限、部署與在線人數檢查。

獨立於 SBOMScan 的供應商授權管理環境，使用官方 Keygen CE API 及官方 Portal 原始碼。SBOMScan 產品端已接入授權驗證；這個目錄屬於供應商端，不隨客戶產品交付。

同一台主機另開獨立測試產品（HTTPS 9443）的指令，請看 [Docker 測試操作](manual/操作手冊.md#在同一台主機另開-docker-測試產品)，使用 `product-test.compose.yaml` 與既有映像，不共用產品資料卷。

## SBOMScan 產品與客戶授權

管理架構為「供應商 Keygen CE＋Portal → 客戶持有 License Key／Machine File → SBOMScan Go API」。管理員 Token、簽章私鑰、Keygen 資料庫和本目錄 `.env` 都留在供應商端。

在供應商主機建立／補齊產品目錄：

```sh
python3 ./product.py init
```

此命令會建立獨立的 `SBOMScan` Product，以及 Basic／Professional／Enterprise 三個評估用 Policy。現階段三者均使用相同的測試額度與模組，尚未定義正式商業方案；之後從 Portal 調整即可。Policy 使用 `MIXED` authentication strategy，讓客戶能以自己的 License Key 啟用設備，不需要供應商管理員 Token。

`init` 會向 API 確認本機目錄中的 Product、Policy 和 Entitlement 是否仍存在。若產品已刪除，會先將舊目錄保存在 `.runtime/product-catalog.stale-時間戳.json`，再建立新產品與評估方案；不會還原已刪除的客戶 License。新 Product ID 會寫入 `product-public.env`，既有產品部署也需要更新其公開設定。輸出的 Portal Products 連結可直接用來核對畫面。

Keygen 的 non-floating Policy 限定 `maxMachines=1`。因此產品 Policy 設為 `floating=true`，讓每張 License 的 `maxMachines` 能表示客戶可啟用的部署數量；`requireHeartbeat` 與 `requireCheckIn` 預設關閉，設備會持續占用部署名額，直到人工釋放。這個設定不會把部署名額變成 Concurrent Users；在線人數仍由各套產品的 Session 分別管理。升級後首次 `init`／`issue` 會一次性修正舊版未定案評估 Policy 的 floating 設定，保留其功能模組與額度；之後不覆寫 Portal 的此項設定。

功能代碼對應如下：

| Entitlement | 產品端執行限制 |
|---|---|
| `SBOMSCAN_SCAN` | 上傳、手動／自動／排程掃描、重新掃描 |
| `SBOMSCAN_COLLECTOR` | Trace Collector 建置、下載與匯入入口 |
| `SBOMSCAN_REMEDIATION` | 修補紀錄與附件寫入 |
| `SBOMSCAN_VULNDB_UPDATE` | 漏洞資料庫更新／匯入及更新排程 |

### 線上或首次連線啟用

以下日期、數量及客戶信箱僅示範；必須換成實際核准的商業條件：

```sh
python3 ./product.py issue \
  --customer customer@example.com --plan Basic \
  --expires 2027-10-17T00:00:00Z --deployments 2 --concurrent-users 10
```

命令會使用既有客戶，或在 Keygen 建立客戶 User，將其設為 License Owner，並設定期限、部署數量與每套部署的在線人數。License Key 寫入權限 0600 的私有交付紀錄，不顯示在終端輸出。

產品端使用 `.runtime/product-public.env` 的公開 Account ID、Product ID 及 Ed25519 公鑰，填入客戶部署的根目錄 `.env`。公開設定不含管理權限，但其來源必須可信。`LICENSE_API_URL` 應改為供應商實際的 HTTPS 網域。

客戶管理員登入 SBOMScan，前往「設定 → 產品授權」，輸入其 License Key。Keygen 負責登記設備並限制啟用數量；產品僅儲存供應商簽署的 Machine File。

| `LICENSE_MODE` | 產品行為 |
|---|---|
| `online` | 每分鐘連線驗證並更新簽章檔案；網路中斷可在最近一次成功驗證後寬限 15 分鐘，且不超過簽章檔案與 License 本身的期限 |
| `activation` | 首次連線啟用取得檔案，之後本機驗證；預設檔案期限為 30 天，且仍受 License 到期日限制 |
| `offline` | 完全不呼叫 Keygen；由管理員匯入簽章檔案 |
| `disabled` | 僅限從 Go 原始碼建立的開發版本；正式 Docker 映像以建置時設定拒絕此模式，客戶交付預設為 `offline` |

本機測試連線可加上 `product-local.compose.yaml`，讓客戶產品測試容器透過 Docker 網路使用 `https://keygen.localhost:8443`，並信任 PoC CA。例如在根目錄 `.env` 已填好公開設定及 `LICENSE_MODE=activation` 後：

```sh
./.runtime/docker-compose \
  --project-directory "$SBOMSCAN_SOURCE_DIR" -f "$SBOMSCAN_SOURCE_DIR/docker-compose.yml" -f "$LICENSE_SERVER_DIR/product-local.compose.yaml" \
  up -d --build
```

這會建置完整商業產品（含掃描工具），不是啟動輕量 License Server。此本機網路 override 不隨客戶交付。正式產品使用客戶自己的資料庫與 volumes，不連到 Keygen 的 PostgreSQL。

### 完全離線核發、續約與換機

1. 客戶開啟「設定 → 產品授權」，將設備識別碼交給供應商。
2. 供應商執行相同 `issue` 命令並加入 `--fingerprint <設備識別碼>`，即可核發可匯入的 `.lic` 檔案；客戶設備不需連網。
3. 續約時在 Portal 修改既有 License 的 expiry，並重新 check-out 同一 Machine，交付新檔案；無需建立新客戶或重新計算部署名額。
4. 換機時由供應商在 Portal 人工釋放舊 Machine，再為新設備登記及核發檔案。舊離線檔案在到期前仍可能有效。

可用 `--not-before 2026-11-01T00:00:00Z` 設定開始日；此值放入 License 的 `metadata.not_before` 並隨檔案簽署。產品在開始日前不開放使用；目前匯入／啟用也須等到開始日。Portal 手動核發時，須同時設定 `metadata.plan`、正整數 `metadata.concurrent_users`（或 `maxProcesses`）及所需 Entitlements。

### 產品端限制與資料保存

- API 在認證後集中檢查授權。無授權、過期、驗證失敗或線上寬限期用盡時，仍可登入、查看和匯出既有資料，包括 POST 的 PDF 匯出；寫入與付費功能會被拒絕。更新授權、登出與必要的密碼安全操作仍可使用。
- **在線人數每套部署分別計算。** 同一使用者的多分頁／多 Session 共用一席。前端每 30 秒 Heartbeat，90 秒沒有活動釋放；登出、強制登出、Session 到期或帳號停用會移除其有效 Session。透過同一產品 PostgreSQL 的交易鎖，避免多個 API 副本超額分配。
- Docker 掛載 Host 的 `/etc/machine-id`，加上獨立、持久化的 installation ID 產生設備識別碼。重啟不改變識別碼；換 Host 或建立新的 installation ID 會改變。必須保留 `product_license` volume，且不可將已啟用的 volume 複製給其他部署。
- 簽章檔案與狀態檔以 0600 寫入產品專用 volume，沒有核發授權的私鑰。每次受保護的請求重新檢查期限；掃描、自動掃描、排程與建置也有後端檢查。
- 狀態檔保留已見時間，偵測超過五分鐘的時間回撥。這無法防止客戶同時回復 Host 與磁碟快照，也無法抵擋控制 Host 的人修改程式或設定。
- Keygen 的中央撤銷會在 `online` 模式下一次驗證時生效；`activation`／`offline` 模式以檔案期限為準。

現行交付入口是 Go API＋Next.js；`backend/app` 的 Python API 未在現行 Compose 啟動，因此未把新的授權服務接進舊 Python 路由。獨立的 Python 驗章範例仍保留於本目錄。

### 產品整合驗證（2026-10-17）

Go 全套測試、前端 66 個既有測試及正式建置已通過。使用獨立的產品測試 PostgreSQL、實際 Go API 與真實 Keygen CE，已驗證 License Key 啟用、每部署在線人數與釋放、離線匯入／重啟、跨部署複製拒絕、中央停權／恢復、功能模組限制及真正到期後的唯讀模式。瀏覽器實際從產品「設定 → 產品授權」匯入檔案成功，顯示方案、期限與在線人數上限，沒有 JavaScript page error。

這些測試使用隔離環境；尚未建置或切換完整的客戶產品映像（含所有掃描工具）。管理中心現有的 SBOMScan 評估 License 使用保留網域 `evaluation@sbomscan.example`，不是實際客戶或正式商業方案。

## 啟動與登入

在專案根目錄執行：

```sh
python3 ./poc.py up
```

需求：Linux、Docker Engine、Python 3、Git，以及首次下載所需的網路。啟動程式會在 `.runtime/` 下載並核對 Compose v2.29.7 的官方 SHA-256；不安裝系統套件。Portal 建置使用 host network，解決本機 Docker 建置網路的 DNS 問題。

- Portal：<https://localhost:8443>
- 管理員：`admin@example.com`
- 隨機密碼：本目錄 `.env` 中的 `KEYGEN_ADMIN_PASSWORD`
- API：`https://localhost:8443/v1/accounts/<KEYGEN_ACCOUNT_ID>`
- CA 憑證：`.runtime/root.crt`

HTTPS 使用 Caddy 的本機 CA。瀏覽器首次開啟會顯示未信任的憑證；可將本機 CA 匯入測試瀏覽器的信任設定。程式測試明確使用此 CA 驗證 HTTPS，不關閉憑證驗證。啟動程式不會修改系統信任設定。

登入後可從左側鑰匙圖示進入授權管理。首頁 Metrics 的歷史分析屬於 EE，不能用它顯示的零值判斷 CE 沒有資料；請查看 Licenses、Policies、Products 與 Machines 清單。

僅綁定 `127.0.0.1:8443`。資料庫、Redis、API 及 Portal 容器沒有直接對外開放連接埠。Caddy 將 `/v1/*` 送至 API，其餘路徑送至 Portal；API 上游使用 `api.keygen.localhost` 的 Host，符合 Keygen 的 domain/subdomain 路由條件。瀏覽器不需設定 hosts。

所有密碼、資料庫加密金鑰及 Account ID 首次產生後保留在 `.env`。初始化程式的輸出含有金鑰，因此只寫到本機 `.runtime/setup.log`，權限為 0600。`.env`、`.runtime/` 與測試授權檔案均不進 Git。不要刪除既有 `.env` 後沿用舊資料庫，否則加密金鑰與帳號設定會不一致。

## 版本

| 元件 | 固定版本 |
|---|---|
| Keygen API | `keygen/api:v1.7.2`，API header 使用 `Keygen-Version: 1.8` |
| 官方 Portal | Commit `2d4bb657273528aafdfd725cd7203021a067c742` |
| PostgreSQL | `17.5-alpine` |
| Redis | `7.4-alpine` |
| Caddy | `2.10.2-alpine` |

API 映像版本與 REST API 版本各自獨立。Portal 的 Account ID 與 API 位址在建置時寫入公開前端設定，管理員密碼與 API Token 不放入前端映像。

官方 API 映像啟用 frozen Bundler，設定 `NO_SENTRY` 會改變 Gemfile 而使啟動失敗，因此保持未設定；也未提供 Sentry DSN。背景工作使用官方預設的 Sidekiq concurrency 10，以符合內建 bulk processing 的連線池需求。PoC 不設定 SendGrid，因此沒有寄信與密碼重設郵件。

## 驗證

```sh
python3 ./poc.py check
python3 ./smoke.py
```

`smoke.py` 另需 Python `cryptography` 套件。此環境已具備。它會透過真實 REST API 建立可重用的測試資料，並核對：

- 管理員密碼登入與 API 1.8。
- Basic、Professional、Enterprise 三個測試 Policy。
- 已啟用指紋可驗證，其他指紋被拒絕。
- 第二台設備超過 `maxMachines=1` 時被拒絕。
- 第三個 Process 超過 `maxProcesses=2` 時被拒絕；測試結束釋放 Process。
- 核發 TTL 30 天、綁定設備且包含 `POC_SCAN` Entitlement 的 Machine File。
- 本機驗證簽章、檔案期限與 License 期限；拒絕修改內容、不同指紋與過期檔案。

三個 Policy 的額度均為測試值，**不代表正式商業方案**。測試設備指紋 `sbomscan-poc-host-001` 是固定的模擬機器碼，尚未整合 Docker Host 硬體指紋。

測試狀態及 License Key 存在 `.runtime/fixtures.json`；簽章檔案為 `.runtime/machine.lic`，信任的 Ed25519 公鑰為 `.runtime/ed25519-public-key.txt`。測試用登入 Token 一小時到期，且會在測試結束時撤銷。

2026-10-17 本機驗證結果：上述 API 與離線測試全部通過；禁止 Python 建立 socket 時仍可完成離線驗證。Headless Chromium 已實際登入並確認 Policies、Products、Licenses、Machines 四個頁面顯示真實測試資料，沒有 JavaScript page error。再次執行 `poc.py up` 亦成功保留資料並通過健康檢查。瀏覽器驗證的截圖保留在 `.runtime/portal-*.png`。

可單獨執行不呼叫 API 的離線驗證：

```sh
python3 ./verify_offline.py \
  ./.runtime/machine.lic \
  --public-key ./.runtime/ed25519-public-key.txt \
  --fingerprint sbomscan-poc-host-001
```

這是 Go／Python 商業系統整合前的 Python 驗證範例。正式整合須固定信任公鑰、從本機取得設備指紋，並把驗證結果接入業務權限。授權檔案與公鑰不能一起接受不受信任來源任意替換。

## 管理

```sh
python3 ./poc.py status
python3 ./poc.py logs
python3 ./poc.py restart
python3 ./poc.py down
```

`down` 只停止並移除此 PoC 的容器及網路，保留資料 volumes；再次 `up` 不會重新載入 schema 或建立帳號。首次啟動失敗可查看 `.runtime/launch.log`；初始化失敗查看含敏感資訊的 `.runtime/setup.log`。不要公開這些檔案。

若 `product.py init` 在 TLS 握手時出現 connection reset／timeout，先執行 `poc.py check`。容器顯示 Running 不代表主機至 8443、容器 DNS 或容器間連線都正常；可執行 `poc.py restart` 重建本 PoC 的容器與網路，再重跑原命令。此操作保留 PostgreSQL、Redis、Caddy 的 volumes 與既有帳號／授權，不重新執行 setup，也不重新建置映像。CLI 的本機 HTTPS 連線不使用環境代理，且仍驗證本機 CA。

## 正式導入仍需確認

- 正式商業方案的額度、功能組合與客戶交付流程。
- VM／硬體變更容忍度，以及客戶可回復磁碟快照時的時間保護策略。
- 備份與還原時保留產品的 installation ID 和授權狀態。
- 生產部署的外部網域、可信 HTTPS、備份還原及維運規範。

完全離線的舊檔案不會即時得知中央撤銷或換機；仍需依檔案／License 到期日失效。上方 `smoke.py` 的 Process 測試是 Keygen API 能力測試；商業產品實際的 Concurrent Users 由產品 Session 與共用資料庫交易鎖執行，依已確認需求，每套部署分別計算。

## 上游來源與條款

- [Keygen API 與 FCL 條款](https://github.com/keygen-sh/keygen-api)
- [官方自行部署文件](https://keygen.sh/docs/self-hosting/)
- [官方 Portal 與 Apache 2.0 條款](https://github.com/keygen-sh/keygen-portal)
- [官方離線授權文件](https://keygen.sh/docs/choosing-a-licensing-model/offline-licenses/)

CE 可免費自行部署商用；FCL 的競爭用途限制及 EE 功能限制仍適用。此部署沒有修改或繞過受授權保護的功能。
