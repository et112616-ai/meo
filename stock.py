import os
import re
import json
import logging
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from mplfinance.original_flavor import candlestick_ohlc
from flask import Flask, request, jsonify
import requests

# 初始化 Flask
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# 初始化 Imgur 客户端
IMGUR_CLIENT_ID = os.environ.get("IMGUR_CLIENT_ID", "a1b2c3d4e5f6g7h")

# 固定股票對應表防呆
STOCK_NAME_MAP = {
    "1101": "台泥", "2330": "台積電", "2454": "聯發科", "2317": "鴻海",
    "2404": "漢唐", "3801": "綠界科技", "3037": "欣興", "2303": "聯電",
    "2022": "聚亨", "2301": "光寶科", "2634": "漢翔", "4979": "華星光",
    "2337": "旺宏"
}

def get_stock_info(raw_id):
    """🧠 鐵壁防呆判斷：先看是不是純數字，再看是不是中文"""
    digits_only = re.sub(r'[^0-9]', '', raw_id)
    if digits_only:
        stock_id = digits_only[:10]
    else:
        stock_id = None
        clean_name = raw_id.replace("K線", "").replace("即時", "").replace("期貨", "").replace("現貨", "").replace("法人", "").replace("持股", "").replace("融資券", "").strip()
        if clean_name:  # 防呆：確保不是空字串才比對
            for code, name in STOCK_NAME_MAP.items():
                if clean_name in name or name in clean_name:
                    stock_id = code
                    break
    
    if not stock_id:
        return None, None
        
    # 補上台股後綴
    ticker = f"{stock_id}.TW" if int(stock_id) < 10000 else f"{stock_id}.TWO"
    return stock_id, ticker

def draw_kline(df, stock_title):
    """繪製 K 線圖並上傳至 Imgur"""
    if df.empty:
        return None
        
    df = df.copy()
    df['Date_Num'] = mdates.date2num(df.index)
    
    fig, ax = plt.subplots(figsize=(10, 6), dpi=100)
    ohlc = df[['Date_Num', 'Open', 'High', 'Low', 'Close']].values
    candlestick_ohlc(ax, ohlc, width=0.6, colorup='red', colordown='green', alpha=0.8)
    
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.xaxis.set_major_locator(mdates.MaxNLocator(10))
    plt.xticks(rotation=30)
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.title(f"{stock_title} K-Line Chart", fontsize=14)
    plt.tight_layout()
    
    img_path = f"temp_{int(datetime.now().timestamp())}.png"
    plt.savefig(img_path)
    plt.close()
    
# 🚀 原生不求人：直接用 requests POST 到 Imgur API
    try:
        url = "https://api.imgur.com/3/image"
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        with open(img_path, "rb") as image_file:
            payload = {"image": image_file.read()}
            response = requests.post(url, headers=headers, files=payload)
        
        # 刪除本地暫存圖
        if os.path.exists(img_path):
            os.remove(img_path)
            
        if response.status_code == 200:
            res_json = response.json()
            return res_json.get("data", {}).get("link")
        else:
            logging.error(f"Imgur API 報錯: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        logging.error(f"Imgur 原生上傳發生異常: {e}")
        if os.path.exists(img_path):
            os.remove(img_path)
    return None

@app.route('/get_chart', methods=['POST'])
def get_chart():
    req_data = request.get_json() or {}
    raw_id = req_data.get('stock_id', '').strip()
    period_type = req_data.get('data', '1d').strip()
    reply_token = req_data.get('replyToken', '').strip()
    
    stock_id, ticker = get_stock_info(raw_id)
    if not stock_id:
        return jsonify({"replyToken": reply_token, "is_text": True, "text": f"抱歉，找不到與「{raw_id}」相關的股票。"}), 200

    stock_name = STOCK_NAME_MAP.get(stock_id, stock_id)
    is_future_state = "future" in period_type
    
    # 決定抓取天數
    days_back = 180 if "1w" in period_type else 60
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    try:
        df = yf.download(ticker, start=start_date)
        if df.empty:
            return jsonify({"replyToken": reply_token, "is_text": True, "text": f"暫時無法取得 {stock_name}({stock_id}) 的走勢資料。"}), 200
            
        # 繪製圖表
        img_url = draw_kline(df, f"{stock_name}({stock_id})")
        if not img_url:
            img_url = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800" # 備用防空網址
            
        latest_price = round(float(df['Close'].iloc[-1]), 2)
        alt_text = f"{stock_name} 雙態查詢結果"
        current_time_str = datetime.now().strftime('%m/%d %H:%M')
        
        # 🗂️ 拼裝完美的 LINE 官方 Flex Message 結構
        bubble_payload = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "xs",
                "contents": [
                    {"type": "text", "text": f"{stock_name} ({stock_id})", "weight": "bold", "size": "xl"},
                    {"type": "text", "text": f"最新收盤價: {latest_price} TWD", "size": "md", "color": "#555555"},
                    {"type": "text", "text": f"更新時間: {current_time_str}", "size": "xs", "color": "#aaaaaa"},
                    {"type": "image", "url": f"{img_url}?t={int(datetime.now().timestamp())}", "size": "full", "aspectMode": "fit", "aspectRatio": "4:3"}
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "xs",
                        "contents": [
                            {"type": "button", "style": "primary", "height": "sm", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} spot"}},
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} 1d"}}
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id} spot"}},
                            {
                                "type": "button", 
                                "height": "sm", 
                                "style": "secondary" if is_future_state else "primary", 
                                "action": {
                                    "type": "message", 
                                    "label": "期現貨" if is_future_state else "期貨", 
                                    "text": f"K線 {stock_id} daily spot" if is_future_state else f"K線 {stock_id} daily future"
                                }
                            }
                        ]
                    }
                ]
            }
        }
        return jsonify({"replyToken": reply_token, "is_text": False, "altText": alt_text, "bubble": json.dumps(bubble_payload, ensure_ascii=False)}), 200        
    except Exception as e:
        logging.error(f"處理 K 線圖表失敗: {e}")
        return jsonify({"replyToken": reply_token, "is_text": True, "text": "後台繪圖運算發生異常，請稍後再試。"}), 200

# ----------------- 其餘三大分流分佈（持股、資券、法人）保持骨架完整 -----------------

@app.route('/get_holders', methods=['POST'])
def get_holders():
    req_data = request.get_json() or {}
    raw_id = req_data.get('stock_id', '').strip()
    reply_token = req_data.get('replyToken', '').strip()
    stock_id, _ = get_stock_info(raw_id)
    stock_name = STOCK_NAME_MAP.get(stock_id, "未知個股")
    
    bubble_payload = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"📊 {stock_name} ({stock_id}) 大股東持股明細", "weight": "bold", "size": "md"},
                {"type": "text", "text": "（此處為模擬大股東籌碼數據佔位）", "size": "sm", "margin": "md"}
            ]
        }
    }
    return jsonify({"replyToken": reply_token, "is_text": False, "bubble": bubble_payload}), 200

@app.route('/get_margin', methods=['POST'])
def get_margin():
    req_data = request.get_json() or {}
    raw_id = req_data.get('stock_id', '').strip()
    reply_token = req_data.get('replyToken', '').strip()
    stock_id, _ = get_stock_info(raw_id)
    stock_name = STOCK_NAME_MAP.get(stock_id, "未知個股")
    
    bubble_payload = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"📈 {stock_name} ({stock_id}) 信用融資融券明細", "weight": "bold", "size": "md"},
                {"type": "text", "text": "（此處為模擬資券增減數據佔位）", "size": "sm", "margin": "md"}
            ]
        }
    }
    return jsonify({"replyToken": reply_token, "is_text": False, "bubble": bubble_payload}), 200

@app.route('/get_legal_deal', methods=['POST'])
def get_legal_deal():
    req_data = request.get_json() or {}
    raw_id = req_data.get('stock_id', '').strip()
    reply_token = req_data.get('replyToken', '').strip()
    stock_id, _ = get_stock_info(raw_id)
    stock_name = STOCK_NAME_MAP.get(stock_id, "未知個股")
    
    bubble_payload = {
        "type": "bubble",
        "body": {
            "type": "box", "layout": "vertical", "contents": [
                {"type": "text", "text": f"🏢 {stock_name} ({stock_id}) 三大法人買賣超", "weight": "bold", "size": "md"},
                {"type": "text", "text": "（此處為外資、投信、自營商買賣數據佔位）", "size": "sm", "margin": "md"}
            ]
        }
    }
    return jsonify({"replyToken": reply_token, "is_text": False, "bubble": bubble_payload}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
