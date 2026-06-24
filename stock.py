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

import re

def normalize_stock_input(stock_input):
    """
    【區域三】智能校正核心：將用戶輸入的 2330 / 台積電 / 2313 / 華通 
    統一轉換為 yfinance 專用的 (stock_id, stock_name)
    """
    if not stock_input:
        return None, None

    # 強制轉字串並去空格、轉大寫
    stock_input = str(stock_input).strip().upper()
    
    # 移除可能不小心帶入的 .TW 後綴，以便進行內部核心庫對照
    stock_input = stock_input.replace(".TW", "")

    # ─── 1. 建立常用核心股票權重對照表 (確保極速精準回應) ───
    # 這裡可以直接加入你最常觀測的口袋名單
    STOCK_DICTIONARY = {
        "2330": "台積電",
        "2313": "華通",
        "1101": "台泥",
        "2022": "聚亨",
        "2301": "光寶科",
        "2303": "聯電",
        "2634": "漢翔",
        "0052": "富邦科技",
        "009816": "凱基台灣TOP50"
    }

    # 反向字典：建立「名稱 ➔ 代碼」的對照 (如 "華通": "2313")
    REVERSE_DICTIONARY = {v: k for k, v in STOCK_DICTIONARY.items()}

    # ─── 2. 判斷輸入型態並進行對齊 ───
    
    # 情況 A：用戶輸入純數字代碼 (例如 "2313" 或 "2330")
    if stock_input.isdigit():
        stock_id = stock_input
        # 從對照表抓名稱，抓不到就給預設的 "個股"
        stock_name = STOCK_DICTIONARY.get(stock_id, "個股")
        
    # 情況 B：用戶輸入中文字名稱 (例如 "華通" 或 "台積電")
    elif stock_input in REVERSE_DICTIONARY:
        stock_name = stock_input
        stock_id = REVERSE_DICTIONARY[stock_name]
        
    # 情況 C：用戶輸入了不在常用表內的非數字 (嘗試用模糊比對)
    else:
        # 如果有查到包含該關鍵字的常用股票
        matched_name = next((name for name in REVERSE_DICTIONARY if stock_input in name), None)
        if matched_name:
            stock_name = matched_name
            stock_id = REVERSE_DICTIONARY[matched_name]
        else:
            # 萬一真的完全找不到，就把用戶輸入當成代碼，名稱給預設
            stock_id = stock_input
            stock_name = "個股"

    # ─── 3. 格式化輸出 ───
    # yfinance 台灣市場必須加上 .TW (例如 2313.TW)，但 ETF 009816 如果格式特殊可另外判斷
    if not stock_id.endswith(".TW") and len(stock_id) <= 4:
        yfinance_id = f"{stock_id}.TW"
    else:
        yfinance_id = stock_id

    return yfinance_id, stock_name
    
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
# 【區域五】 核心進入點與標準 LINE Flex 封裝外殼 (Controller & Flask API Wrapper)
# ==============================================================================
from flask import Flask, request, jsonify

# 🔥 關鍵：宣告 app 變數，讓 Render 的 Gunicorn 能夠順利抓到它！
app = Flask(__name__)

@app.route('/get_chart', methods=['POST'])
def webhook_entry():
    """
    接收來自 Make (Integromat) 的 HTTP POST 請求窗口
    """
    try:
        # 1. 抓取 Make 傳過來的 JSON 資料
        payload = request.get_json()
        if not payload:
            return jsonify(build_error_response("未接收到 JSON Payload")), 400
            
        # 2. 丟進主控制器處理雙向轉換與按鈕分流
        response_data = handle_request(payload)
        
        # 3. 將算好的完美 LINE Flex JSON 原封不動回傳給 Make
        return jsonify(response_data), 200
        
    except Exception as e:
        return jsonify(build_error_response(f"後台大腦發生非預期錯誤: {str(e)}")), 500


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

def build_flex_image_response(stock_id, stock_name, title, image_url, current_mode, price_info="--", change_info="--", time_stamp="--", time_frame="D"):
    """ 🛡️ 系統最高防禦準則：完全體圖片型 Flex Bubble 外殼 (100% 符合規格書) """
    
    # 依據目前選定的時間週期，動態調整按鈕顏色 (選中的變成 primary 綠色，其餘為 secondary 灰色)
    def get_tf_style(tf):
        return "primary" if time_frame == tf else "secondary"

    return {
        "type": "flex",
        "altText": f"{stock_id} {stock_name} {title} 觀測儀表板",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "md",
                "contents": [
                    # ─── 一、 頂部基本資訊區 ───
                    {
                        "type": "box",
                        "layout": "vertical",
                        "marginBottom": "md",
                        "contents": [
                            { "type": "text", "text": f"{stock_id} {stock_name}", "weight": "bold", "size": "xl", "color": "#111111" },
                            { "type": "text", "text": f"{price_info}  ({change_info})", "weight": "bold", "size": "md", "color": "#FF3B30" if "+" in change_info else "#34C759" },
                            { "type": "text", "text": f"更新時間：{time_stamp}", "size": "xs", "color": "#8E8E93", "margin": "xs" }
                        ]
                    },
                    # ─── 中上排：時間週期橫排按鈕 ───
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "xs",
                        "marginBottom": "md",
                        "contents": [
                            { "type": "button", "style": get_tf_style("1m"), "height": "sm", "action": { "type": "postback", "label": "1分", "data": f"stock={stock_id}&action={current_mode}&current_mode={current_mode}&time_frame=1m" } },
                            { "type": "button", "style": get_tf_style("5m"), "height": "sm", "action": { "type": "postback", "label": "5分", "data": f"stock={stock_id}&action={current_mode}&current_mode={current_mode}&time_frame=5m" } },
                            { "type": "button", "style": get_tf_style("D"), "height": "sm", "action": { "type": "postback", "label": "D", "data": f"stock={stock_id}&action={current_mode}&current_mode={current_mode}&time_frame=D" } },
                            { "type": "button", "style": get_tf_style("W"), "height": "sm", "action": { "type": "postback", "label": "W", "data": f"stock={stock_id}&action={current_mode}&current_mode={current_mode}&time_frame=W" } },
                            { "type": "button", "style": get_tf_style("M"), "height": "sm", "action": { "type": "postback", "label": "M", "data": f"stock={stock_id}&action={current_mode}&current_mode={current_mode}&time_frame=M" } }
                        ]
                    },
                    # ─── 二、 中間：核心大圖區 (白底高解析度) ───
                    {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": "#FFFFFF",
                        "cornerRadius": "md",
                        "borderWidth": "1px",
                        "borderColor": "#E5E5EA",
                        "contents": [
                            { "type": "image", "url": image_url, "size": "full", "aspectMode": "fit", "aspectRatio": "4:3" }
                        ]
                    }
                ]
            },
            # ─── 三、 底部：操作面板與資料走線 ───
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    # 底部第一排（模式切換）
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "sm",
                        "contents": [
                            { "type": "button", "style": "primary" if current_mode == "instant" else "secondary", "action": { "type": "postback", "label": "即時", "data": f"stock={stock_id}&action=instant&current_mode=instant&time_frame={time_frame}" } },
                            { "type": "button", "style": "primary" if current_mode == "k_line" else "secondary", "action": { "type": "postback", "label": "K線", "data": f"stock={stock_id}&action=k_line&current_mode=k_line&time_frame={time_frame}" } }
                        ]
                    },
                    # 底部第二排（籌碼與連動）
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "xs",
                        "contents": [
                            { "type": "button", "style": "primary" if current_mode == "legal_person" else "secondary", "height": "sm", "action": { "type": "postback", "label": "法人", "data": f"stock={stock_id}&action=legal_person&current_mode=legal_person" } },
                            { "type": "button", "style": "secondary", "height": "sm", "action": { "type": "postback", "label": "大戶", "data": f"stock={stock_id}&action=large_holder&current_mode={current_mode}" } },
                            { "type": "button", "style": "secondary", "height": "sm", "action": { "type": "postback", "label": "融資券", "data": f"stock={stock_id}&action=margin&current_mode={current_mode}" } },
                            { "type": "button", "style": "secondary", "height": "sm", "action": { "type": "postback", "label": "期貨", "data": f"stock={stock_id}&action=futures&current_mode={current_mode}&time_frame={time_frame}" } }
                        ]
                    }
                ]
            }
        }
    }
def build_flex_text_table_response(stock_id, stock_name, title, data_list, table_type):
    """ 🛡️ 統一外殼防爆器：輸出純文字小表格型 Bubble JSON 結構 """
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
                ]
            }
        }
    }

def build_error_response(error_msg):
    return {"status": "error", "message": error_msg}

# 確保本地測試時也可以跑
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
