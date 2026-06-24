# -*- coding: utf-8 -*-
"""
專案名稱：台股期現貨籌碼觀測機器人
維護人員：蔡秉璋 (2026 最終優化版)
最高架構：5 大模組清晰分區，嚴格對齊 LINE Flex Message 100% 防爆規範
"""

import os
import datetime
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ==============================================================================
# 【區域一】 環境配置與全域宣告 (Environment & Fonts Config)
# ==============================================================================
# 徹底解決 Linux/Windows 伺服器上的中文烘焙字型問題，防止圖表出現中文字變形或方塊 [口口]
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'Arial', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False  # 完美顯示負數的減號 (-)

# 模擬台股個股與名稱對照表快取 (實際運行可改為讀取 DB 或證交所 API)
MOCK_STOCK_DATABASE = {
    "2330": "台積電",
    "2303": "聯電",
    "2454": "聯發科",
}

# ==============================================================================
# 【區域二】 智能雙向校正核心 (Stock ID & Name Normalizer)
# ==============================================================================
def get_stock_name_by_id(stock_id):
    return MOCK_STOCK_DATABASE.get(stock_id, "未知股票")

def get_stock_id_by_name(stock_name):
    for k, v in MOCK_STOCK_DATABASE.items():
        if v == stock_name:
            return k
    return None

def normalize_stock_input(stock_input):
    """
    實作秉璋指定的『雙向模糊比對』：
    - 輸入 "2330"   -> 查出 "台積電"，回傳 ("2330", "台積電")
    - 輸入 "台積電" -> 查出 "2330"，回傳 ("2330", "台積電")
    """
    stock_input_clean = str(stock_input).strip()
    
    if stock_input_clean.isdigit():
        stock_id = stock_input_clean
        stock_name = get_stock_name_by_id(stock_id)
    else:
        stock_name = stock_input_clean
        stock_id = get_stock_id_by_name(stock_name)
        
    return stock_id, stock_name

def convert_to_futures_id(stock_id):
    """將個股代碼轉換為對應的個股期貨代碼"""
    return f"F_{stock_id}"

def upload_to_cloud(fig):
    """
    【圖片上傳中繼站】
    將 Matplotlib 的 fig 物件轉為圖片並上傳，回傳實體 URL 供 LINE 渲染。
    (此處先以靜態示意網址代替，實際佈署時可串接 Imgur API 或伺服器目錄)
    """
    plt.close(fig) # 釋放記憶體以免後台爆掉
    return "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=500"


# ==============================================================================
# 【區域三】 Matplotlib 數據繪圖引擎 (Graphic Rendering Engine)
# ==============================================================================
def generate_instant_plot(stock_id, stock_name, is_futures=False):
    """ 模式 A：即時走勢圖 (江波圖) """
    fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
    # [繪圖邏輯] 繪製盤中價格連續折線圖...
    ax.plot([1, 2, 3, 4], [5, 7, 6, 8], color='#1e88e5', lw=2)
    ax.set_title(f"{stock_name}({stock_id}) {'期貨' if is_futures else ''} 即時走勢")
    
    image_url = upload_to_cloud(fig)
    return build_flex_image_response(stock_id, stock_name, "即時走勢", image_url, current_mode="instant")

def generate_k_line_plot(stock_id, stock_name, time_frame="D", is_futures=False):
    """ 模式 B：專業技術 K 線圖 (帶均線、成交量雙子圖) """
    fig = plt.figure(figsize=(6, 4), dpi=100)
    gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
    
    # 子圖 1：K線與均線
    ax_k = fig.add_subplot(gs[0])
    ax_k.set_title(f"{stock_name}({stock_id}) {time_frame}K線圖")
    # 子圖 2：紅綠成交量柱狀圖
    ax_vol = fig.add_subplot(gs[1])
    
    image_url = upload_to_cloud(fig)
    return build_flex_image_response(stock_id, stock_name, f"{time_frame}K線圖", image_url, current_mode="k_line")

def generate_legal_person_chart(stock_id, stock_name):
    """ 
    模式 C：三大法人籌碼觀測大圖 
    ★ 嚴格執行秉璋指令：垂直獨立三大區域、最新數據頂部內嵌、X軸日期隱藏壓縮
    """
    # 創建 3 列 1 行的畫布
    fig, axes = plt.subplots(3, 1, figsize=(7, 9), dpi=120)
    fig.suptitle(f"【{stock_name} {stock_id}】10日三大法人籌碼分布", fontsize=14, fontweight='bold')
    
    # 模擬 10 天的買賣超數據 (正數為買超、負數為賣超)
    mock_10d_data = [1200, -850, 430, 2100, -1500, 600, -300, 900, -450, 2300]
    colors = ['#e63946' if x > 0 else '#2a9d8f' for x in mock_10d_data] # 買超紅、賣超綠
    
    investor_types = [
        {"title": "▋ 第一區域：外資 (Foreign Investment)", "ratio": "45.23%", "today": "+2,300"},
        {"title": "▋ 第二區域：投信 (Investment Trust)", "ratio": "3.45%", "today": "+450"},
        {"title": "▋ 第三區域：自營商 (Dealer)", "ratio": "1.12%", "today": "-150"}
    ]
    
    for i, ax in enumerate(axes):
        info = investor_types[i]
        
        # 1. 頂部內嵌第一排文字核心資訊 (日期、持股比、當日買賣超張數)
        text_str = f"最新日期: 06/23  │  持股比: {info['ratio']}  │  當日買賣超: {info['today']} 張"
        ax.text(0.02, 1.15, text_str, transform=ax.transAxes, fontsize=10, fontweight='bold', color='#1d3557')
        
        # 2. 第二排繪製 10 日橫式柱狀圖趨勢 (以長條圖呈現 10 日起伏)
        ax.bar(range(10), mock_10d_data, color=colors, edgecolor='none', width=0.6)
        ax.axhline(0, color='#6c757d', linewidth=0.8) # 繪製 Y=0 基準線
        
        # 3. 欄位極致縮小防爆：徹底隱藏 X 軸日期序列字樣
        ax.set_xticklabels([])
        ax.set_xticks([])
        
        # 裝飾調整
        ax.set_ylabel("張數", fontsize=9)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_title(info['title'], loc='left', fontsize=11, fontweight='bold', pad=25, color='#e63946' if i==0 else '#2a9d8f')

    plt.tight_layout()
    image_url = upload_to_cloud(fig)
    return build_flex_image_response(stock_id, stock_name, "三大法人籌碼", image_url, current_mode="legal_person")


# ==============================================================================
# 【區域四】 籌碼純文字表格生成器 (Text Table Generator)
# ==============================================================================
def generate_large_holder_table(stock_id, stock_name):
    """ 大戶按鈕：集保千張大戶持股比率 (直列 3 排純文字小表格，由新到舊共 6 排) """
    # 模擬 6 週歷史數據
    weeks_data = [
        {"date": "06/18", "ratio": "65.42%", "diff": "+0.23%"},
        {"date": "06/12", "ratio": "65.19%", "diff": "-0.05%"},
        {"date": "06/05", "ratio": "65.24%", "diff": "+0.11%"},
        {"date": "05/29", "ratio": "65.13%", "diff": "+0.02%"},
        {"date": "05/22", "ratio": "65.11%", "diff": "-0.45%"},
        {"date": "05/15", "ratio": "65.56%", "diff": "+0.08%"}
    ]
    return build_flex_text_table_response(stock_id, stock_name, "大戶持股週報", weeks_data, table_type="large_holder")

def generate_margin_table(stock_id, stock_name):
    """ 融資券按鈕：信用交易狀況 (橫排對齊純文字小表格，由新到舊共 10 排) """
    # 模擬 10 天信用交易數據，資券比已在後台經由 (融券/融資)*100% 計算完畢並帶上 %
    margin_data = [
        {"date": "6/23", "long": "12450", "short": "1200", "ratio": "9.64%"},
        {"date": "6/22", "long": "12100", "short": "1250", "ratio": "10.33%"},
        {"date": "6/19", "long": "11950", "short": "1100", "ratio": "9.21%"},
        {"date": "6/18", "long": "12000", "short": "1050", "ratio": "8.75%"},
        {"date": "6/17", "long": "12200", "short": "980",  "ratio": "8.03%"},
        {"date": "6/16", "long": "12150", "short": "1020", "ratio": "8.40%"},
        {"date": "6/15", "long": "11800", "short": "950",  "ratio": "8.05%"},
        {"date": "6/12", "long": "11900", "short": "900",  "ratio": "7.56%"},
        {"date": "6/11", "long": "11750", "short": "880",  "ratio": "7.49%"},
        {"date": "6/10", "long": "11600", "short": "850",  "ratio": "7.33%"}
    ]
    return build_flex_text_table_response(stock_id, stock_name, "融資券10日動態", margin_data, table_type="margin")


# ==============================================================================
# 【區域五】 核心進入點與標準 LINE Flex 封裝外殼 (Controller & Standard Flex Wrapper)
# ==============================================================================
def handle_request(payload):
    """ 主入口：接收來自 Make 的參數，自動雙向轉換，並依狀態記憶繼承分流 """
    stock_input = payload.get("stock")
    action = payload.get("action")
    current_mode = payload.get("current_mode", "instant")
    time_frame = payload.get("time_frame", "D")
    
    # 啟動智能校正
    stock_id, stock_name = normalize_stock_input(stock_input)
    if not stock_id:
        return build_error_response(f"找不到「{stock_input}」相關的股票資料，請重新檢查輸入")
    
    # 【期貨連動與狀態繼承邏輯】
    if action == "futures":
        futures_id = convert_to_futures_id(stock_id)
        if current_mode == "legal_person":
            return generate_instant_plot(futures_id, stock_name, is_futures=True)
        elif current_mode == "k_line":
            return generate_k_line_plot(futures_id, stock_name, time_frame, is_futures=True)
        else:
            return generate_instant_plot(futures_id, stock_name, is_futures=True)

    # 標準一般按鈕分流
    if action == "instant":
        return generate_instant_plot(stock_id, stock_name)
    elif action == "k_line":
        return generate_k_line_plot(stock_id, stock_name, time_frame)
    elif action == "legal_person":
        return generate_legal_person_chart(stock_id, stock_name)
    elif action == "large_holder":
        return generate_large_holder_table(stock_id, stock_name)
    elif action == "margin":
        return generate_margin_table(stock_id, stock_name)
    else:
        return build_error_response("未知的操作指令")

def build_flex_image_response(stock_id, stock_name, title, image_url, current_mode):
    """ 🛡️ 統一外殼防爆器：輸出圖片型 Bubble JSON 結構 """
    # 這裡未來會填入完整的 LINE Flex Message 階層結構，包含頂部3排、中上週期、中間大圖、下排按鈕
    return {
        "type": "flex",
        "altText": f"{stock_id} {stock_name} {title} 觀測儀表板",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    { "type": "text", "text": f"{stock_id} {stock_name}", "weight": "bold", "size": "xl" },
                    { "type": "image", "url": image_url, "size": "full", "aspectMode": "cover" }
                    # 下方保留傳遞參數按鈕，並打包 current_mode 回傳給 Make
                ]
            }
        }
    }

def build_flex_text_table_response(stock_id, stock_name, title, data_list, table_type):
    """ 🛡️ 統一外殼防爆器：輸出純文字小表格型 Bubble JSON 結構 (骨架與上方圖片型完全一致) """
    # 這裡最外層結構維持不變，僅中間肚子抽換成文字 Box 積木排版
    return {
        "type": "flex",
        "altText": f"{stock_id} {stock_name} {title} 觀測數據",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    { "type": "text", "text": f"{stock_id} {stock_name} - {title}", "weight": "bold" }
                    # 依據 table_type 在此迴圈渲染直列三排(大戶)或橫排對齊(融資券)的 Text 元件
                ]
            }
        }
    }

def build_error_response(error_msg):
    return {"status": "error", "message": error_msg}
