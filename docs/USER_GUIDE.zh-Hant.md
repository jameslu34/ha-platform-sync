# 裝置平台同步：完整使用手冊

> 適用版本：0.6.4
> 中文名稱：裝置平台同步
> English name: Cross-Platform Device Sync

「裝置平台同步」是 Home Assistant 的自訂整合。它可以把一組指定的裝置，
自動同步到 Google Home、HomeKit 或 Matterbridge。

這份手冊以一般使用者為主，不需要了解程式設計。

## 目錄

1. [這個外掛在做什麼](#這個外掛在做什麼)
2. [開始前要準備什麼](#開始前要準備什麼)
3. [安裝外掛](#安裝外掛)
4. [第一次設定](#第一次設定)
5. [如何選擇同步來源](#如何選擇同步來源)
6. [如何選擇目標平台](#如何選擇目標平台)
7. [額外加入與排除怎麼用](#額外加入與排除怎麼用)
8. [如何暫停與重新啟用](#如何暫停與重新啟用)
9. [外掛什麼時候會同步](#外掛什麼時候會同步)
10. [如何修改設定](#如何修改設定)
11. [預覽與立即同步](#預覽與立即同步)
12. [規劃各平台的安全規則](#規劃各平台的安全規則)
13. [常見問題](#常見問題)
14. [更新或移除外掛](#更新或移除外掛)
15. [快速設定範例](#快速設定範例)

## 這個外掛在做什麼

這個外掛監視的是：

> **哪些裝置應該出現在各個智慧家庭平台。**

例如，您可以指定：

- 以 Home Assistant 某幾個儀表板頁面中的裝置為準。
- 自己手動勾選一組裝置。
- 以目前 HomeKit、Google Home 或 Matterbridge 中的裝置為準。
- 再選擇要同步到 Google Home、HomeKit、Matterbridge 中的哪些平台。

它會自動比較來源與目標：

- 沒有變更時，不會重複同步。
- 有新增裝置時，加入已選的目標平台。
- 有移除裝置時，從已選的目標平台移除曝光。
- 各平台可以另外指定一定要加入或一定要排除的裝置。
- 更新失敗時，會盡量回復到更新前的設定。

每個已勾選目標都會收斂成精確清單：`（來源 − 該平台排除）∪ 該平台額外加入`，
再套用相容性與受保護規則。即使某個裝置在安裝外掛前就已存在於目標，只要它不在
最終清單中，也會從此外掛管理的曝光設定移除。未勾選的目標平台不會被修改。

### 它不會做什麼

這個外掛不會：

- 開燈、關燈或切換任何開關。
- 控制門鎖、保全、空調、攝影機或媒體播放。
- 因為溫度、亮度或其他感測值改變就重新同步。
- 刪除 Home Assistant 裡的裝置或實體。
- 複製儀表板的卡片樣式與版面配置。
- 建立額外的感測器或按鈕實體。

它只管理「裝置是否顯示在目標平台」。

## 開始前要準備什麼

第一次啟用前，建議先建立一份 Home Assistant 完整備份。

只需要準備您打算使用的平台：

| 平台 | 事前準備 |
|---|---|
| Google Home | 先完成 Home Assistant 的 Google Assistant 整合與 Google 帳號連結 |
| HomeKit | 先在 Home Assistant 建立並配對 HomeKit Bridge 或 Accessory |
| Matterbridge | 先安裝並啟用 Matterbridge，以及 `matterbridge-hass` 外掛 |

如果只使用手動來源或 Home Assistant 儀表板來源，不需要先設定所有三個平台；
只要準備您勾選的目標平台即可。

### Google Home 目標的必要設定

Google Home 作為目標時，需要使用獨立的裝置設定檔。預設檔名是：

`google_assistant_entity_config.yaml`

Google Assistant 必須關閉「預設曝光全部裝置」。相關設定可合併到原本的
Google Assistant 設定中：

~~~yaml
google_assistant:
  expose_by_default: false
  entity_config: !include google_assistant_entity_config.yaml
~~~

請不要因此刪除原本 Google Assistant 需要的其他設定。如果您不熟悉 YAML，
建議先請熟悉 Home Assistant 的管理者完成這項一次性設定。

### HomeKit 的必要設定

- HomeKit 作為來源時：先建立可正常使用的 HomeKit Bridge／Accessory。
- HomeKit 作為目標時：先決定哪些 HomeKit Bridge／Accessory 可以交給此外掛更新。
- Apple 家庭 App 內原生配對的裝置，不會出現在 HomeKit 來源選單中。

### Matterbridge 的必要設定

- Matterbridge 必須正在運作。
- `matterbridge-hass` 必須已安裝、啟用並連上 Home Assistant。
- 準備 Matterbridge 的主機名稱、IP，或完整安全管理端點，以及管理連接埠。
- 若 Matterbridge 已啟用前端驗證，請準備前端密碼。
- 預設管理連接埠是 `8283`。

## 安裝外掛

### 建議方式：使用 HACS 安裝

本專案採用原始碼公開的非商業授權，因此請用 HACS 自訂儲存庫安裝；它不會列入
HACS 預設目錄。

1. 如果尚未安裝 HACS，請先完成 HACS 安裝與設定。
2. 開啟**自訂儲存庫**，在 **Repository** 欄位輸入
   `jameslu34/ha-platform-sync`，類別選擇**整合**。
3. 在 HACS 找到 **Cross-Platform Device Sync** 並點選**下載**。
4. 建立 Home Assistant 備份。
5. 重新啟動 Home Assistant。

也可以使用 GitHub 專案 README 裡的 **Open in HACS** 按鈕加入自訂存放庫。

### 手動安裝

1. 從 GitHub 下載最新 Release。
2. 將 `custom_components/platform_sync` 資料夾複製到
   `/config/custom_components/platform_sync`。
3. 確認中間沒有多包一層資料夾。
4. 建立 Home Assistant 備份。
5. 重新啟動 Home Assistant。

### 新增整合

1. 前往**設定 → 裝置與服務 → 整合**。
2. 點選右下角的**新增整合**。
3. 搜尋：

   - 中文介面：**裝置平台同步**
   - 英文介面：**Cross-Platform Device Sync**

4. 點選整合並開始設定。

此整合只需要建立一個設定項目。如果已經安裝過，請直接打開原本的設定。

## 第一次設定

設定畫面會依您的選擇自動顯示下一步需要的內容，不需要一次填完所有平台。

### 第 1 步：選擇同步來源

畫面上有兩個主要選項：

- **啟用同步**：勾選後開始使用跨平台同步。
- **同步來源**：選擇哪一組裝置要當作同步基準。

如果不勾選「啟用同步」，按**下一步**後會直接完成設定，不會再要求其他資料。

### 第 2 步：設定來源

下一頁會依來源顯示不同內容：

| 同步來源 | 下一頁會顯示 |
|---|---|
| Home Assistant 儀表板中的裝置 | 選擇一個或多個儀表板頁面 |
| 手動選取的裝置 | 直接勾選實體 |
| HomeKit 中的裝置 | 勾選 HomeKit Bridge／Accessory 設定項目 |
| Google Home 中的裝置 | 直接前往選擇目標平台 |
| Matterbridge 中的裝置 | 直接前往選擇目標平台，連線資料稍後填寫 |

### 第 3 步：選擇目標平台

至少勾選一個要同步到的平台：

- Google Home
- HomeKit
- Matterbridge

### 第 4 步：設定已選平台

只會顯示您有勾選的平台設定。

例如：

- 只勾 Google Home，就不會看到 HomeKit 的額外加入與排除設定。
- 只勾 HomeKit，就不會看到 Google Home 的設定檔欄位。
- Matterbridge 若被選為來源，仍需填寫主機與連接埠。

### 第 5 步：確認設定

最後一頁會顯示：

- 是否啟用
- 選擇的來源
- 選擇的目標平台
- 儀表板頁面或 HomeKit 來源項目

確認無誤後送出。完成最後一步前，外掛不會先修改任何目標平台。

## 如何選擇同步來源

### Home Assistant 儀表板中的裝置

適合希望「儀表板上有哪些裝置，其他平台就同步哪些裝置」的使用者。

設定方式：

1. 選擇「Home Assistant 儀表板中的裝置」。
2. 按下一步。
3. 複選一個或多個儀表板頁面。
4. 按下一步選擇目標平台。

多個頁面中的裝置會合併，重複裝置只計算一次。

如果頁面沒有出現在選單中，可以選擇手動輸入路徑。例如：

- 儀表板路徑：`lovelace`
- 頁面路徑：`default-view`

請不要同時勾選頁面清單與手動輸入路徑。

注意：

- 每個選取的頁面都必須可以正常讀取。
- 所選頁面至少要有一個裝置實體。
- 外掛同步裝置清單，不會同步卡片外觀或排列順序。

### 手動選取的裝置

適合希望完全自己決定裝置清單的使用者。

設定方式：

1. 選擇「手動選取的裝置」。
2. 按下一步。
3. 勾選一個或多個實體。
4. 按下一步選擇目標平台。

之後若要新增或移除裝置，需要回到此外掛設定中修改。裝置的開關狀態不會改變
這份清單。

### Google Home 中的裝置

適合希望以 Home Assistant 目前提供給 Google Home 的裝置清單為準。

選擇後會直接前往目標平台頁面，不需要再選一次裝置。

注意：

- 讀取的是 Home Assistant Google Assistant 整合中的清單。
- 不是直接登入 Google Home App 讀取原生裝置。
- 需要先完成 Google Assistant 整合。

### HomeKit 中的裝置

選擇後，下一頁會用核取方塊列出 Home Assistant 中的 HomeKit
Bridge／Accessory。

設定方式：

1. 勾選一個或多個要作為來源的 HomeKit 項目。
2. 按下一步選擇目標平台。

注意：

- 勾選的是整個 HomeKit Bridge／Accessory 設定項目。
- 不是在此頁逐一勾選項目內的每一個實體。
- 不是 Apple 家庭 App 內原生配對的裝置。
- 任一被選項目失效時，外掛會停止本次同步，不會只同步剩下的一部分。

### Matterbridge 中的裝置

適合希望以 Matterbridge 現有裝置清單為準。

選擇後會直接前往目標平台頁面。Matterbridge 的主機或完整端點、連接埠與
選填的前端密碼，會在稍後的平台設定頁出現。

注意：

- Matterbridge 與 `matterbridge-hass` 必須已正常運作。
- 外掛會使用 Matterbridge 的精確裝置清單。
- 不使用 Home Assistant 標籤來決定同步裝置。

## 如何選擇目標平台

### Google Home

勾選 Google Home 後，需要設定：

- **Google Assistant 裝置設定檔**
- 選填的「Google Home 額外加入」
- 選填的「Google Home 排除」

同步成功後，外掛會通知 Google Home 重新取得裝置清單。

### HomeKit

勾選 HomeKit 後，需要選擇：

- **可更新的 HomeKit 目標項目**
- 選填的「HomeKit 額外加入」
- 選填的「HomeKit 排除」

只會更新您在此處明確勾選的 HomeKit Bridge／Accessory。作為來源的 HomeKit
項目，不會因為被選為來源就自動取得修改權限。
若要讓外掛長期自動更新，主 HomeKit Bridge 必須透過 Home Assistant UI 建立。
YAML 管理的項目仍可作為唯讀來源，也能以「固定且精確的單一實體 Accessory」留在
受管理目標配置中；外掛不會改寫這類匯入 Accessory，避免 Home Assistant 重啟後又
被 YAML 覆寫回去。

### Matterbridge

勾選 Matterbridge 後，需要設定：

- Matterbridge 主機
- Matterbridge 連接埠
- 選填的「Matterbridge 密碼」
- 選填的「Matterbridge 額外加入」
- 選填的「Matterbridge 排除」

有變更時，外掛會更新裝置清單並重新載入 `matterbridge-hass`。

## 額外加入與排除怎麼用

每個目標平台都有自己的例外設定。

除「額外加入」及受保護規則保留的項目外，已勾選目標中所有不在來源的既有曝光都會
移除；「排除」中的項目即使存在於來源也不會加入。這裡的移除只取消此外掛管理的
平台曝光，不會刪除 Home Assistant 實體，也不會解除原生平台配對。

### 額外加入

即使來源中沒有這個裝置，也要讓指定平台包含它。

範例：

- 某個虛擬按鈕只需要出現在 Google Home。
- 將它加入「Google Home 額外加入」。
- 不需要加入 HomeKit 或 Matterbridge。

### 排除

即使來源中有這個裝置，也不要同步到指定平台。

範例：

- 儀表板中有一台已原生配對 HomeKit 的燈。
- 將它放入「HomeKit 排除」，避免重複出現。
- 它仍可同步到 Google Home 或 Matterbridge。

注意：

- 同一個裝置不能同時放在同一平台的「額外加入」與「排除」。
- 每個平台的設定彼此獨立。
- 沒有勾選的平台不會顯示相關欄位。
- 未勾選平台原本的例外設定會保留，日後重新勾選仍可繼續使用。

## 如何暫停與重新啟用

### 暫時停用

1. 前往**設定 → 裝置與服務 → 整合**。
2. 找到**裝置平台同步**。
3. 點選**設定**。
4. 取消勾選**啟用同步**。
5. 按**下一步**。

設定會立即完成。

停用後，外掛不會：

- 監視來源變更
- 定期檢查來源
- 在 Home Assistant 開機時執行同步
- 更新任何目標平台

原本的來源、目標與例外設定會保留。

停用不會撤銷上一次已同步的裝置。Google Home、HomeKit 與 Matterbridge 會保留
停用當下的裝置清單。

### 重新啟用

1. 再次打開整合設定。
2. 勾選**啟用同步**。
3. 依畫面重新確認來源與目標。
4. 完成最後確認。

重新啟用後會先完整檢查一次，再決定是否需要更新平台。

## 外掛什麼時候會同步

### Home Assistant 開機後

只要「啟用同步」有勾選，Home Assistant 或此外掛啟動後一定會完整檢查一次。

### 儀表板來源有變更時

儀表板或相關實體資料有變化時，通常會很快開始檢查。短時間內的多次變更會合併，
避免重複同步。

### HomeKit 來源有變更時

外掛會優先使用 HomeKit 設定變更通知。若目前的 Home Assistant 版本無法使用
通知機制，才會改成定期檢查。

已明確選取的可更新 HomeKit 目標若發生設定變更，也會立即觸發重新檢查。平台仍在
啟動時不會阻止保存完整設定，之後會由有上限的背景重試等待收斂。

### Google Home 或 Matterbridge 作為來源時

大約每 15 秒檢查一次裝置清單。偵測到變更後才會開始同步。

### Matterbridge 自動復原

啟用同步後，背景檢查也會確認 Matterbridge、`matterbridge-hass`、精確裝置清單
與已載入裝置都已就緒。若只有執行狀態異常，且安全條件全部成立，外掛會先等待
Matterbridge 備份真正完成，再優先重新啟動 Home Assistant 外掛；精確讀回仍未
收斂時，才會重新啟動完整 Matterbridge 程序。開機後先保留三分鐘啟動寬限期，
避免正常載入過程誤觸重啟。每個故障階段最多執行一次，並保留五分鐘冷卻時間。
持續失敗時，重試間隔依序為 15、30、60、120、300 秒。

如果管理介面無法連線、缺少憑證、外掛已停用、精確清單為空或不一致，或有其他
篩選器正在作用，系統不會自動重啟。停用同步時，也會一併停用這項自動復原。

### 手動來源

不需要定期檢查。只有修改整合設定、重新啟動或手動執行同步時才會重新計算。

### 沒有變更時

外掛只會記錄「沒有變更」，不會：

- 重複通知 Google Home
- 重載 HomeKit
- 重新載入 Matterbridge
- 控制任何裝置

## 如何修改設定

此外掛不會建立設定用實體。請從整合頁修改：

**設定 → 裝置與服務 → 整合 → 裝置平台同步 → 設定**

可以修改：

- 是否啟用
- 同步來源
- 儀表板頁面或手動裝置
- 目標平台
- 各平台額外加入與排除
- Google Assistant 設定檔
- 可更新的 HomeKit 項目
- Matterbridge 連線資料

再次開啟**設定**時，所有已儲存參數都會自動回填。若某個欄位驗證失敗，當頁其他
剛輸入的內容不會消失。取消勾選某個目標平台時，該平台的連線資料、額外加入與排除
會暫時隱藏且不生效，但仍會保存；日後重新勾選便會完整恢復。

## 預覽與立即同步

一般使用者平時不需要使用這兩個進階功能。

### 預覽同步

前往**開發者工具 → 動作**，選擇：

`platform_sync.preview`

它只會顯示預計新增或移除的內容，不會修改平台。重大調整前可先用它確認結果。

### 立即同步

前往**開發者工具 → 動作**，選擇：

`platform_sync.sync_now`

它會立刻檢查並套用必要變更，不必等待下一次自動檢查。

如果「啟用同步」沒有勾選，這兩個動作都不會讀取或更新來源。

## 規劃各平台的安全規則

每個家庭的裝置不同。啟用同步前，請先找出只應出現在單一平台的裝置，以及已經
原生配對、不應重複曝光的裝置。

以下使用泛用的虛擬實體作為示範：

- `input_boolean.google_presence` 只需要出現在 Google Home。
- `input_boolean.apple_presence` 只需要出現在 HomeKit。
- `input_boolean.someone_arrived` 需要出現在 Google Home 與 HomeKit，但不需要
  出現在 Matterbridge。

可以在各目標平台分別設定：

| 範例實體 | Google Home | HomeKit | Matterbridge |
|---|---:|---:|---:|
| `input_boolean.google_presence` | 額外加入 | 排除 | 排除 |
| `input_boolean.apple_presence` | 排除 | 額外加入 | 排除 |
| `input_boolean.someone_arrived` | 額外加入 | 額外加入 | 排除 |

這些只是範例，不是此外掛內建的實體或預設規則。請在各平台的「額外加入」與
「排除」欄位選擇自己的實體。

HomeKit 目標也建議視情況排除：

- 已直接在 Apple 家庭原生配對的裝置，避免產生重複配件。
- 已透過 Apple 原生配對使用，而且由 Home Assistant Apple TV 整合提供的媒體
  裝置。

Matterbridge 使用精確裝置清單。此外掛不會建立或依賴專門用於跨平台選取的
Home Assistant 標籤。

## 常見問題

### 找不到「裝置平台同步」

- 確認資料夾位置是
  `/config/custom_components/platform_sync`。
- 確認沒有多包一層資料夾。
- 安裝後重新啟動 Home Assistant。
- 查看 Home Assistant 記錄是否有載入錯誤。

### 找不到想選的儀表板頁面

部分 YAML 或無法自動列出的儀表板不會出現在清單中。請使用「手動輸入儀表板
路徑」，填入網址中的儀表板與頁面路徑。

### 儀表板來源顯示為空

- 確認頁面仍存在並可以開啟。
- 確認頁面中至少放了一個具有實體 ID 的裝置。
- 確認所有被選頁面都可以正常讀取。

### HomeKit 來源不能通過或無法同步

- 確認選的是 Home Assistant HomeKit Bridge／Accessory。
- 暫時尚未載入的項目仍可保存，但要等 HomeKit runtime 已載入且可驗證為執行中，
  才會完成同步。
- 確認項目使用明確的裝置清單，而不是「全部某類裝置」之類的寬鬆條件。
- Apple 家庭原生配對裝置不會出現在這份來源清單中。

### HomeKit 目標沒有可選項目

請先在 Home Assistant 建立並配對 HomeKit Bridge／Accessory，再回到此外掛
設定中選取。外掛不會代替使用者建立或完成 Apple 家庭配對。

若主 Bridge 由 YAML 管理，請改用 Home Assistant UI 重新建立。匯入的單實體
Accessory 可以固定留在已選配置中，但若要更換或移除，必須自行修改 HomeKit YAML；
外掛不會套用重啟後就會消失的匯入 Accessory 暫時變更。

### Google Home 顯示尚未設定完成

確認：

- Google Assistant 整合已載入。
- 已完成 Google 帳號連結。
- 已設定 `expose_by_default: false`。
- 已使用獨立的 Google Assistant 裝置設定檔。
- 設定檔路徑是相對路徑，不是完整磁碟路徑。

### Matterbridge 無法連線

確認：

- 主機名稱、IP，或完整 ws／wss／http／https 端點正確。
- 管理連接埠正確。
- 選填的前端密碼正確。
- WSS 端點的憑證可被 Home Assistant 信任。
- Matterbridge 正在運作。
- `matterbridge-hass` 已啟用並連上 Home Assistant。

### 同步成功，但手機 App 還沒看到

外掛可以確認 Home Assistant 端與平台連接端的設定，但 Google Home、
Apple 家庭或 Matter 控制器 App 仍可能需要一些時間更新。

如果 App 仍未顯示，請：

1. 稍候片刻再重新開啟 App。
2. 確認帳號、家庭與 Bridge 配對正確。
3. 在原生 App 中手動確認。

這種情況應理解為「Home Assistant 端已完成，原生 App 尚未確認」。

### 同步失敗

1. 先不要連續重按「立即同步」。
2. 打開整合設定，檢查來源與目標平台是否仍可使用。
3. 可先執行「預覽同步」查看預計變更。
4. 在整合選單中下載診斷資料。
5. 若畫面顯示回復未完成，請使用 Home Assistant 或平台備份進行還原。

分享診斷資料前，仍應確認內容中沒有密碼、Token、Cookie、私鑰或 API key。

## 更新或移除外掛

### 更新

1. 暫時關閉「啟用同步」。
2. 建立 Home Assistant 完整備份。
3. 用新版本覆蓋 `custom_components/platform_sync`。
4. 重新啟動 Home Assistant。
5. 打開整合設定，確認來源、目標與例外規則。
6. 仔細確認所有設定後再重新啟用；送出最後確認頁就會開始自動檢查。

升級後，舊版的設定會盡量安全保留。舊版的第二個自動套用開關、輪詢時間、
合併等待時間、自訂名稱與狀態實體已不再使用。

### 移除

移除整合只會停止後續管理，不會自動撤銷最後一次同步的裝置清單。

如果要回到安裝前的狀態：

1. 先停用同步。
2. 使用 Home Assistant 或各平台備份還原。
3. 確認三個平台的裝置清單。
4. 從「裝置與服務」移除整合。
5. 刪除 `/config/custom_components/platform_sync`。
6. 重新啟動 Home Assistant。

## 快速設定範例

### 需求

以 Home Assistant 首頁為準，同步到 Google Home、HomeKit 與 Matterbridge。

### 操作

1. 新增「裝置平台同步」整合。
2. 勾選「啟用同步」。
3. 選擇「Home Assistant 儀表板中的裝置」。
4. 選擇首頁所在的儀表板頁面，例如 `lovelace / default-view`。
5. 目標勾選 Google Home、HomeKit、Matterbridge。
6. 填入 Google Assistant 裝置設定檔。
7. 勾選可更新的 HomeKit 目標項目。
8. 填入 Matterbridge 端點、連接埠與選填密碼。
9. 視需要設定各平台的額外加入與排除。
10. 在確認頁檢查後送出。

之後：

- Home Assistant 或外掛啟動時會檢查一次。
- 首頁裝置變更時會自動重新計算。
- 沒有差異時不會重複更新平台。
- 有差異時才會同步並驗證。

## 授權方式

從 0.6.1 版開始，本外掛採用
[PolyForm Noncommercial License 1.0.0](../LICENSE)。使用者可以在授權允許的
非商業用途下查看、使用、修改及分享原始碼或修改版，但不得用於商業用途。

這是「原始碼公開的非商業授權」，不是 OSI 核准的開放原始碼授權。0.6.1
以前的版本仍適用當時隨附的授權條款。

---

Home Assistant 使用繁體中文時顯示「裝置平台同步」；使用英文時顯示
「Cross-Platform Device Sync」。兩種語言的功能與設定流程相同。
