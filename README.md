# LicenseServer

獨立的供應商授權管理專案：一套 Keygen CE + Portal，管理多套 SBOMScan。
本專案不需要 SBOMScan 原始碼即可啟動。Keygen 核心使用官方容器映像，並非本專案自行實作。

```text
LicenseServer（供應商，集中部署一次）
  ├─ 客戶 A / SBOMScan（獨立資料庫、授權檔與部署識別）
  ├─ 客戶 B / SBOMScan（獨立資料庫、授權檔與部署識別）
  └─ 客戶 C / SBOMScan（獨立資料庫、授權檔與部署識別）
```

## Windows Docker 一鍵啟動

先啟動 Docker Desktop（Linux containers），在本資料夾開啟 PowerShell：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\docker-start.ps1
```

不需額外安裝 Ubuntu、Python 或 Git。腳本會自動產生 `.env`、下載映像、初始化資料庫、建置 Portal、啟動服務並建立 SBOMScan 評估方案。首次啟動需要連網；後續重跑會保留設定與資料。

啟動完成後開啟 **https://localhost:8443**。新環境預設登入帳號 **`admin`**、密碼 **`admin123`**；登入頁會將 `admin` 對應至 `.env` 的 `KEYGEN_ADMIN_EMAIL`（預設 `admin@example.com`），也可直接輸入該 Email。密碼保存在 `.env` 的 `KEYGEN_ADMIN_PASSWORD`。本機 CA 位於 `.runtime/root.crt`，瀏覽器需信任此憑證。

這組預設值用於首次初始化，密碼不寫入 Docker 映像。既有資料庫不會因重新 build 或修改 `.env` 而重設管理員密碼；已有帳號請從管理介面修改，並同步更新 `.env`。重建 Portal 會套用 `.env` 中管理員 Email 的簡寫對應。

```powershell
.\docker-start.ps1 status
.\docker-start.ps1 check
.\docker-start.ps1 logs
.\docker-start.ps1 down
```

Docker Desktop 會將服務顯示在同一個 `sbomscan-keygen-poc` Compose 專案內。PostgreSQL、Redis、Keygen、Portal 與 Caddy 各自使用容器；`down` 保留資料卷。不要使用 `docker compose down -v`，該命令會刪除資料卷。備份時需保存資料庫、`.env` 與 `.runtime`。

完成第一次初始化後，也可用 `docker compose up -d` 啟動既有容器。此配置只提供本機存取；正式公開服務請見下方「集中服務與交付」。

## 專案額度

在「授權原則 → 編輯」設定「每套部署的專案額度」，在「授權 → 新增／編輯」為客戶指定額度或勾選「不限專案數」。正整數代表每套部署的上限，`-1` 代表不限；額度會寫入 License 的 `metadata.max_projects` 並隨 Machine File 簽章。政策預設只在配發時複製，之後不會自動改寫已配發授權。

`product.py init` 補齊 Trial（3 個）與 Basic（5 個）的缺少預設值，保留既有自訂值。Professional／Enterprise 不代替供應商決定額度；先在方案設定或核發時用 `--max-projects` 指定。例如：

```powershell
py -3 product.py issue --customer customer@example.com --plan Basic --expires 2027-10-24T00:00:00Z --deployments 1 --concurrent-users 10 --max-projects 5
# 不限：將 --max-projects 改為 -1。
```

既有 License 不會被初始化工具偷偷修改。升級 SBOMScan 後，舊授權若缺少專案額度會禁止建立新專案；在 Keygen 補上該張 License 的專案額度，再從原 Machine Checkout 新 `.lic` 並匯入產品即可。請先備妥新檔再升級正式客戶。

## 進階功能

「元件」管理與「Webhook」預設隱藏。前往 **設定 → 一般 → 管理介面 → 進階功能**，按 **啟用進階功能** 後，才會顯示元件入口、設備頁元件連結、設備簽出的元件關聯選項，以及 Webhook 端點與事件頁面。再次按 **關閉進階功能** 可隱藏。這項偏好儲存在目前瀏覽器，切換時會重新載入頁面；請先儲存正在編輯的表單。此設定只調整介面顯示，既有資料及 Webhook 傳送設定會保留。

## 介面語言

Portal 預設使用繁體中文，在 **設定 → 一般 → 管理介面 → 介面語言** 可切換 **繁體中文（台灣）／English (United States)**，並記住此瀏覽器的偏好。登入與其他頁面不顯示浮動語言選單。切換會重新載入目前頁面，請先儲存編輯中的表單。客戶資料、產品與方案名稱、授權金鑰及技術代碼保留原值。

翻譯字典隨映像提供，不呼叫第三方翻譯服務。翻譯維護與驗證方式見 [portal-i18n/README.md](portal-i18n/README.md)。

## Linux 本機驗證

`poc.py` 是 Linux 本機測試啟動器，會下載 Linux Compose 執行檔。Windows 請使用上方 Docker 啟動腳本。
在本專案根目錄執行：

```sh
python3 poc.py up
python3 product.py init
```

Portal：`https://localhost:8443`。管理員密碼在本專案 `.env`。
客戶端公開設定輸出至 `.runtime/product-public.env`。

```sh
python3 product.py issue --customer customer@example.com --plan Basic \
  --expires 2027-10-19T00:00:00Z --deployments 1 --concurrent-users 10
```

不同客戶分別核發 License；同一客戶需要多套部署時，設定相應 `--deployments`。
在線人數依每套 SBOMScan 分別計算，不是跨所有客戶共用的總額。

## 集中服務與交付

正式服務必須另行設定可由客戶連線的 HTTPS 網域、憑證、Keygen 主機設定及 Portal 主機設定。
現有 `compose.yaml`、`Caddyfile` 和 `poc.py` 保留 loopback 本機測試設定，並非直接對外上線配置。
設定公開網址後可輸出客戶連線設定：

```sh
LICENSE_PUBLIC_URL=https://licenses.example.com python3 product.py init
```

這個變數只設定交付檔中的網址，不會自動設定 DNS、TLS 或開放連接埠。
每套 SBOMScan 使用相同的 `LICENSE_API_URL`、Account ID、Product ID、公鑰，客戶各持自己的 License Key。
完全離線的客戶改由此服務核發簽章 Machine File，無須持續連線。

只交付公開設定、客戶 License Key／Machine File；供應商 `.env`、`.runtime`、管理員 Token、私鑰及資料庫都保留在此服務。
備份本服務 PostgreSQL、`.env` 與 `.runtime`；既有資料移轉時保留 Compose 專案名與資料卷。

## 跨專案整合測試

只有測試客戶產品時才需要 SBOMScan checkout／映像。從本專案根目錄執行，路徑使用絕對路徑：

```sh
export SBOMSCAN_SOURCE_DIR=/absolute/path/SBOMScan
export LICENSE_SERVER_DIR=/absolute/path/LicenseServer

# 使用 SBOMScan 自己的 .env；測試 override 只用於本機信任 CA。
docker compose --project-directory "$SBOMSCAN_SOURCE_DIR" \
  -f "$SBOMSCAN_SOURCE_DIR/docker-compose.yml" \
  -f "$LICENSE_SERVER_DIR/product-local.compose.yaml" up -d --build

# 獨立產品測試環境，先準備 sbomscan-backend-go:latest 與 sbomscan-frontend:latest。
docker compose -p sbomscan-license-test --env-file .runtime/product-public.env \
  -f product-test.compose.yaml up -d

python3 audit.py
```

不需服務的設定匯出測試：`python3 -m unittest test_product_export`。

`audit_ui.py` 是針對已執行前端的瀏覽器測試，需要額外安裝 Playwright／Chromium。
完整操作參考 [OPERATIONS.md](OPERATIONS.md) 與 [圖文手冊](manual/操作手冊.md)。跨專案 Compose 指令以本頁為準。

## 拆分紀錄

從 `payton8905/SBOMScan` 的 `b56bff472fcecdbdc65839c0f18219f320978883` 中抽出原 `deployment/keygen/`。
此目錄是獨立 Git 儲存庫；尚未設定遠端。原 SBOMScan 的歷史提交仍保留原目錄，拆分不會改寫歷史。
