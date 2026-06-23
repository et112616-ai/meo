import os
import io
import requests
import json
import re
import pandas as pd
from flask import Flask, request, jsonify, send_file
import yfinance as yf
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import twstock
import threading

app = Flask(__name__)

# ==========================================
# 🌟 核心升級 1：證交所全自動連線初始化邏輯（防卡死快取版）
# ==========================================
STOCK_NAME_MAP = {
    "1101": "台泥", "2022": "聚亨", "2301": "光寶科", "2303": "聯電",
    "2313": "華通", "2330": "台積電", "2337": "旺宏", "2634": "漢翔",
    "4979": "華星光", "0052": "富邦科技", "009816": "凱基台灣TOP50"
}

def init_twstock_data():
    global STOCK_NAME_MAP
    print("⏳ 正在背景連線台灣證交所下載最新個股清單...")
    try:
        twstock.__update_codes()
        dynamic_map = {}
        for code, info in twstock.codes.items():
            if info.type in ['股票', 'ETF', '台灣存託憑證(TDR)', '受益證券']:
                dynamic_map[code] = info.name
        if dynamic_map:
            STOCK_NAME_MAP.update(dynamic_map)
            print(f"🎉 證交所資料同步成功！目前共支援 {len(STOCK_NAME_MAP)} 檔台股名稱。")
    except Exception as e:
        print(f"⚠️ 證交所連線失敗，將維持核心持股清單。錯誤: {str(e)}")

threading.Thread(target=init_twstock_data, daemon=True).start()

# ==========================================
# 🌟 核心升級 2：Matplotlib 繁體中文支援中心
# ==========================================
CHINESE_FONT_NAME = None

def setup_chinese_font():
    global CHINESE_FONT_NAME
    try:
        system_fonts = [f.name for f in fm.fontManager.ttflist]
        fallback_fonts = ['Noto Sans CJK TC', 'Microsoft JhengHei', 'Arial Unicode MS', 'Heiti TC', 'Droid Sans Fallback']
        
        for font in fallback_fonts:
            if font in system_fonts:
                CHINESE_FONT_NAME = font
                break
                
        if CHINESE_FONT_NAME:
            matplotlib.rc('font', family=CHINESE_FONT_NAME)
            plt.rcParams['axes.unicode_minus'] = False
            print(f"🎉 成功啟用系統中文字體：{CHINESE_FONT_NAME}")
            return

        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTC/NotoSansCJK-Regular.ttc"
        font_path = os.path.join(os.getcwd(), "NotoSansCJK-Regular.ttc")
        if not os.path.exists(font_path):
            r = requests.get(font_url, stream=True)
            if r.status_code == 200:
                with open(font_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk: f.write(chunk)
        if os.path.exists(font_path):
            font_prop = fm.FontProperties(fname=font_path)
            CHINESE_FONT_NAME = font_prop.get_name()
            matplotlib.rc('font', family=CHINESE_FONT_NAME)
            fm.fontManager.addfont(font_path)
            plt.rcParams['axes.unicode_minus'] = False
            print(f"🎉 成功動態載入中文字體：{CHINESE_FONT_NAME}")
    except Exception as e:
        print(f"⚠️ 中文字體初始化失敗：{str(e)}")

setup_chinese_font()

@app.route('/images/<image_key>.png', methods=['GET'])
def serve_image(image_key):
    filepath = f"{image_key}.png"
    if os.path.exists(filepath):
        return send_file(filepath, mimetype='image/png')
    return "Image not found", 404

# -------------------------------------------------------------------------
# 🛠️ 路由 2：【K線圖主控中心】
# -------------------------------------------------------------------------
@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        action_data = req_data.get('data', '').strip()
        reply_token = req_data.get('replyToken', '').strip()

        stock_id = re.sub(r'[^a-zA-Z0-9]', '', raw_id.replace("K線", "").replace("即時", ""))[:10]
        if not stock_id:
            return jsonify({"error": "Missing stock_id"}), 400

        if '1m' in action_data: period, interval, title_text = '1d', '1m', '1分鐘K線'
        elif '3m' in action_data: period, interval, title_text = '1d', '3m', '3分鐘K線'
        elif '5m' in action_data: period, interval, title_text = '1d', '5m', '5分鐘K線'
        elif '30m' in action_data: period, interval, title_text = '5d', '30m', '30分鐘K線'
        elif 'weekly' in action_data: period, interval, title_text = '1y', '1wk', '週K線'
        elif 'monthly' in action_data: period, interval, title_text = '5y', '1mo', '月K線'
        else: period, interval, title_text = '3mo', '1d', '日K線'

        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")
        yf_code = f"{stock_id}.TW"
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty or len(df) < 2:
            body_contents = [{"type": "text", "text": f"{stock_name} 查無足夠 K 線資料。"}]
            footer_contents = []
        else:
            latest_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
            change = latest_close - prev_close
            change_percent = (change / prev_close) * 100
            
            price_string = f"{latest_close:,.2f}"
            change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({change_percent:.2f}%)"
            color_theme = "#ff0000" if change >= 0 else "#008000"

            image_key = f"chart_{stock_id}"
            
            # 💡 傳入中文字體配置，徹底解決圖片中文變亂碼的問題
            font_config = {'fontname': CHINESE_FONT_NAME} if CHINESE_FONT_NAME else {}
            fig, axes = mpf.plot(df, type='candle', volume=True, returnfig=True, figsize=(10, 6), style='yahoo')
            axes[0].set_title(f"{stock_name} ({stock_id}) - {title_text}", fontsize=16, color='black', weight='bold', **font_config)
            
            fig.savefig(f"{image_key}.png", format='png', bbox_inches='tight', dpi=100, facecolor='white')
            plt.close('all')

            base_url = "https://meo-qput.onrender.com"
            final_image_url = f"{base_url}/images/{image_key}.png"

            # 🌟 重新梳理符合 LINE 官方原生規範的完美排版
            body_contents = [
                {
                    "type": "box", "layout": "horizontal", "alignment": "center",
                    "contents": [
                        {"type": "text", "text": f"{stock_name} ({stock_id})", "weight": "bold", "size": "xl", "flex": 3, "gravity": "center"},
                        {"type": "button", "style": "secondary", "height": "sm", "flex": 1, "action": {"type": "message", "label": "期貨", "text": f"期貨 {stock_id}"}}
                    ]
                },
                {"type": "separator", "margin": "md"},
                {
                    "type": "box", "layout": "vertical", "margin": "md",
                    "contents": [
                        {"type": "image", "url": final_image_url, "size": "full", "aspectMode": "cover", "aspectRatio": "20:13"},
                        {
                            "type": "box", "layout": "horizontal", "margin": "md",
                            "contents": [
                                {"type": "text", "text": f"最新價: {price_string}", "weight": "bold", "size": "sm"},
                                {"type": "text", "text": f"漲跌: {change_string}", "weight": "bold", "size": "sm", "color": color_theme, "align": "end"}
                            ]
                        }
                    ]
                }
            ]

            # 🌟 將所有按鈕收納到官方最安全的 footer 區塊，分成四大排
            footer_contents = [
                # 第一排：分時切換
                {
                    "type": "box", "layout": "horizontal", "spacing": "xs",
                    "contents": [
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "1分", "text": f"K線 {stock_id} 1m"}},
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "3分", "text": f"K線 {stock_id} 3m"}},
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "5分", "text": f"K線 {stock_id} 5m"}},
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "30分", "text": f"K線 {stock_id} 30m"}}
                    ]
                },
                # 第二排：日週月切換
                {
                    "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                    "contents": [
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "日", "text": f"K線 {stock_id} daily"}},
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "週", "text": f"K線 {stock_id} weekly"}},
                        {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "月", "text": f"K線 {stock_id} monthly"}}
                    ]
                },
                {"type": "separator", "margin": "sm"},
                # 第三排：功能大鈕 A
                {
                    "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "sm",
                    "contents": [
                        {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id}"}},
                        {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily"}},
                        {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id}"}}
                    ]
                },
                # 第四排：功能大鈕 B
                {
                    "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                    "contents": [
                        {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id}"}},
                        {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id}"}}
                    ]
                }
            ]

        line_payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "flex",
                    "altText": f"{stock_name} ({stock_id}) K線圖查詢結果",
                    "contents": {
                        "type": "bubble",
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "md",
                            "contents": body_contents
                        },
                        "footer": {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "xs",
                            "contents": footer_contents
                        } if footer_contents else None
                    }
                }
            ]
        }
        return jsonify(line_payload), 200

    except Exception as e:
        print(f"💥 K線主控系統崩潰：{str(e)}")
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# 🛠️ 路由 3：【千張大股東籌碼中心】
# -------------------------------------------------------------------------
@app.route('/get_holders', methods=['POST'])
def get_holders():
    # 籌碼中心邏輯維持先前優化版，故不重複贅述以節省空間...
    pass # 請保留你原有的 get_holders 完整語法

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
