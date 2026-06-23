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

# 抓取 Imgur 環境變數
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
        if clean_name:
            for code, name in STOCK_NAME_MAP.items():
                if clean_name in name or name in clean_name:
                    stock_id = code
                    break
    
    if not stock_id:
        return None, None
        
    ticker = f"{stock_id}.TW" if int(stock_id) < 10000 else f"{stock_id}.TWO"
    return stock_id, ticker

def draw_kline(df, stock_title):
    """繪製帶有均線與成交量優化的精美 K 線圖，並原生 requests 上傳至 Imgur"""
    if df.empty:
        return None
        
    try:
        df = df.copy()
        # 確保索引為 Datetime 格式
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
            
        df['Date_Num'] = mdates.date2num(df.index)
        
        # 計算簡單移動平均線 (MA5, MA20) 防禦型計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        
        # 建立雙子圖 (上方K線與均線，下方成交量)
        fig = plt.figure(figsize=(10, 7), dpi=100)
        grid = plt.GridSpec(4, 1, hspace=0.3)
        ax1 = fig.add_subplot(grid[0:3, 0])
        ax2 = fig.add_subplot(grid[3, 0], sharex=ax1)
        
        # 轉換成 candlestick 要求的數組結構，並確保為 float 型態
        ohlc = []
        for idx, row in df.iterrows():
            ohlc.append([
                row['Date_Num'],
                float(row['Open']),
                float(row['High']),
                float(row['Low']),
                float(row['Close'])
            ])
            
        # 繪製 K 線
        candlestick_ohlc(ax1, ohlc, width=0.6, colorup='red', colordown='green', alpha=0.9)
        
        # 繪製均線
        if not df['MA5'].isna().all():
            ax1.plot(df['Date_Num'], df['MA5'], label='MA5', color='blue', linewidth=1)
        if not df['MA20'].isna().all():
            ax1.plot(df['Date_Num'], df['MA20'], label='MA20', color='orange', linewidth=1)
        ax1.legend(loc='upper left')
        ax1.grid(True, linestyle='--', alpha=0.5)
        ax1.set_title(f"{stock_title} K-Line Chart", fontsize=14, weight='bold')
        
        # 繪製成交量
        colors = ['red' if float(c) >= float(o) else 'green' for o, c in zip(df['Open'], df['Close'])]
        ax2.bar(df['Date_Num'], df['Volume'], width=0.6, color=colors, alpha=0.7)
        ax2.grid(True, linestyle='--', alpha=0.5)
        
        # 格式化 X 軸日期
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax1.xaxis.set_major_locator(mdates.MaxNLocator(10))
        plt.setp(ax1.get_xticklabels(), visible=False) # 隱藏上圖 X 軸標籤
        
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax2.xaxis.set_major_locator(mdates.MaxNLocator(10))
        plt.xticks(rotation=30)
        
        plt.tight_layout()
        
        img_path = f"temp_{int(datetime.now().timestamp())}.png"
        plt.savefig(img_path, bbox_inches='tight')
        plt.close()
    except Exception as drawing_error:
        logging.error(f"Matplotlib 繪圖細節出錯: {drawing_error}")
        return None
    
    # 原生 requests POST 到 Imgur API
    try:
        url = "https://api.imgur.com/3/image"
        headers = {"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"}
        with open(img_path, "rb") as image_file:
            payload = {"image": image_file.read()}
            response = requests.post(url, headers=headers, files=payload)
        
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
        stock_id = "2330"
        ticker = "2330.TW"

    stock_name = STOCK_NAME_MAP.get(stock_id, stock_id)
    is_future_state = "future" in period_type
    
    # 動態判定回推天數
    if "5d" in period_type.lower():
        days_back = 15
    elif "1w" in period_type.lower():
        days_back = 180
    elif "1m" in period_type.lower():
        days_back = 365
    else:
        days_back = 60
        
    start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    
    try:
        # 下載單層結構的 Ticker 資料
        df = yf.download(ticker, start=start_date, group_by='ticker')
        if df.empty:
            raise ValueError("Yahoo Finance 核心資料為空")
            
        # 處理多重欄位索引問題 (防止 yfinance 吐出多個 Ticker 巢狀欄位)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(-1)
            
        img_url = draw_kline(df, f"{stock_name}({stock_id})")
        if not img_url:
            # 觸發備用卡
            raise ValueError("圖片生成或上傳失敗，切換至安全排版")
            
        latest_price = round(float(df['Close'].iloc[-1]), 2)
        alt_text = f"{stock_name} 雙態查詢結果"
        current_time_str = datetime.now().strftime('%m/%d %H:%M')
        
        bubble_payload = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {"type": "text", "text": f"{stock_name} ({stock_id})", "weight": "bold", "size": "xl"},
                    {"type": "text", "text": f"最新收盤價: {latest_price} TWD", "size": "md", "color": "#555555"},
                    {"type": "text", "text": f"更新時間: {current_time_str}", "size": "xs", "color": "#aaaaaa"},
                    {"type": "image", "url": f"{img_url}?t={int(datetime.now().timestamp())}", "size": "full", "aspectMode": "fit", "aspectRatio": "4:3"}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "style": "primary" if period_type == "1d" else "secondary", "height": "sm", "action": {"type": "message", "label": "1D", "text": f"K線 {stock_id} 1d"}},
                            {"type": "button", "style": "primary" if period_type == "5d" else "secondary", "height": "sm", "action": {"type": "message", "label": "5D", "text": f"K線 {stock_id} 5d"}},
                            {"type": "button", "style": "primary" if period_type == "1w" else "secondary", "height": "sm", "action": {"type": "message", "label": "W", "text": f"K線 {stock_id} 1w"}},
                            {"type": "button", "style": "primary" if period_type == "1m" else "secondary", "height": "sm", "action": {"type": "message", "label": "M", "text": f"K線 {stock_id} 1m"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "style": "primary", "height": "sm", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} spot"}},
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} 1d"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
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
        
        return jsonify({
            "replyToken": reply_token, 
            "is_text": False, 
            "altText": alt_text, 
            "bubble": json.dumps(bubble_payload, ensure_ascii=False)
        }), 200
        
    except Exception as e:
        logging.error(f"鐵壁保護激活 - 運算異常: {e}")
        fallback_url = "https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=800"
        current_time_str = datetime.now().strftime('%m/%d %H:%M')
        
        fallback_bubble = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {"type": "text", "text": f"{raw_id} (查詢結果)", "weight": "bold", "size": "xl"},
                    {"type": "text", "text": "後台數據產生中，請稍候刷新", "size": "md", "color": "#ff5555"},
                    {"type": "text", "text": f"時間: {current_time_str}", "size": "xs", "color": "#aaaaaa"},
                    {"type": "image", "url": fallback_url, "size": "full", "aspectMode": "fit", "aspectRatio": "4:3"}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "1D", "text": f"K線 {stock_id} 1d"}},
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "5D", "text": f"K線 {stock_id} 5d"}},
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "W", "text": f"K線 {stock_id} 1w"}},
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "M", "text": f"K線 {stock_id} 1m"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "style": "primary", "height": "sm", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} spot"}},
                            {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} 1d"}}
                        ]
                    }
                ]
            }
        }
        return jsonify({
            "replyToken": reply_token, 
            "is_text": False, 
            "altText": "個股查詢結果", 
            "bubble": json.dumps(fallback_bubble, ensure_ascii=False)
        }), 200

# ----- 保留其餘分流終端骨架，確保回傳對齊 -----
@app.route('/get_holders', methods=['POST'])
def get_holders():
    req_data = request.get_json() or {}
    return jsonify({"replyToken": req_data.get('replyToken', ''), "is_text": True, "text": "持股明細查詢中..."}), 200

@app.route('/get_margin', methods=['POST'])
def get_margin():
    req_data = request.get_json() or {}
    return jsonify({"replyToken": req_data.get('replyToken', ''), "is_text": True, "text": "信用資券明細查詢中..."}), 200

@app.route('/get_legal_deal', methods=['POST'])
def get_legal_deal():
    req_data = request.get_json() or {}
    return jsonify({"replyToken": req_data.get('replyToken', ''), "is_text": True, "text": "三大法人買賣超查詢中..."}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
