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

STOCK_NAME_MAP = {
    "1101": "台泥", "2022": "聚亨", "2301": "光寶科", "2303": "聯電",
    "2313": "華通", "2330": "台積電", "2337": "旺宏", "2634": "漢翔",
    "4979": "華星光", "0052": "富邦科技", "009816": "凱基台灣TOP50"
}

def init_twstock_data():
    global STOCK_NAME_MAP
    try:
        twstock.__update_codes()
        dynamic_map = {}
        for code, info in twstock.codes.items():
            if info.type in ['股票', 'ETF', '台灣存託憑證(TDR)', '受益證券']:
                dynamic_map[code] = info.name
        if dynamic_map:
            STOCK_NAME_MAP.update(dynamic_map)
    except Exception as e:
        print(f"⚠️ 證交所連線失敗: {str(e)}")

threading.Thread(target=init_twstock_data, daemon=True).start()

CHINESE_FONT_NAME = None
def setup_chinese_font():
    global CHINESE_FONT_NAME
    try:
        system_fonts = [f.name for f in fm.fontManager.ttflist]
        fallback_fonts = ['Noto Sans CJK TC', 'Microsoft JhengHei', 'Arial Unicode MS', 'Heiti TC']
        for font in fallback_fonts:
            if font in system_fonts:
                CHINESE_FONT_NAME = font
                break
        if CHINESE_FONT_NAME:
            matplotlib.rc('font', family=CHINESE_FONT_NAME)
            plt.rcParams['axes.unicode_minus'] = False
    except Exception as e:
        print(f"⚠️ 中文字體失敗: {str(e)}")

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
            return jsonify({
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": f"{stock_name} 查無足夠 K 線資料。"}]
            }), 200

        latest_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
        change = latest_close - prev_close
        change_percent = (change / prev_close) * 100
        
        price_string = f"{latest_close:,.2f}"
        change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({change_percent:.2f}%)"
        color_theme = "#ff0000" if change >= 0 else "#008000"

        image_key = f"chart_{stock_id}"
        font_config = {'fontname': CHINESE_FONT_NAME} if CHINESE_FONT_NAME else {}
        fig, axes = mpf.plot(df, type='candle', volume=True, returnfig=True, figsize=(10, 6), style='yahoo')
        axes[0].set_title(f"{stock_name} ({stock_id}) - {title_text}", fontsize=16, color='black', weight='bold', **font_config)
        
        fig.savefig(f"{image_key}.png", format='png', bbox_inches='tight', dpi=100, facecolor='white')
        plt.close('all')

        base_url = "https://meo-qput.onrender.com"
        final_image_url = f"{base_url}/images/{image_key}.png"

        # 📦 訊息 1：純圖卡泡泡
        chart_bubble = {
            "type": "flex",
            "altText": f"{stock_name} ({stock_id}) K線圖",
            "contents": {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box", "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": f"📊 {stock_name} ({stock_id})", "weight": "bold", "size": "lg"},
                                {"type": "text", "text": title_text, "size": "sm", "color": "#888888", "align": "end", "gravity": "bottom"}
                            ]
                        },
                        {"type": "separator", "margin": "xs"},
                        {"type": "image", "url": final_image_url, "size": "full", "aspectMode": "cover", "aspectRatio": "20:13", "margin": "sm"},
                        {
                            "type": "box", "layout": "horizontal", "margin": "sm",
                            "contents": [
                                {"type": "text", "text": f"最新價: {price_string}", "weight": "bold", "size": "sm"},
                                {"type": "text", "text": f"漲跌: {change_string}", "weight": "bold", "size": "sm", "color": color_theme, "align": "end"}
                            ]
                        }
                    ]
                }
            }
        }

        # 📦 訊息 2：純按鈕鍵盤泡泡
        buttons_bubble = {
            "type": "flex",
            "altText": f"{stock_name} 功能選單",
            "contents": {
                "type": "bubble",
                "size": "md",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {
                            "type": "box", "layout": "horizontal",
                            "contents": [
                                {"type": "button", "style": "secondary", "height": "sm", "action": {"type": "message", "label": f"➔ 查詢 {stock_name} 期貨", "text": f"期貨 {stock_id}"}}
                            ]
                        },
                        {"type": "separator", "margin": "xs"},
                        {
                            "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                            "contents": [
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "1分", "text": f"K線 {stock_id} 1m"}},
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "3分", "text": f"K線 {stock_id} 3m"}},
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "5分", "text": f"K線 {stock_id} 5m"}},
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "30分", "text": f"K線 {stock_id} 30m"}}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "spacing": "xs",
                            "contents": [
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "日線", "text": f"K線 {stock_id} daily"}},
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "週線", "text": f"K線 {stock_id} weekly"}},
                                {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "月線", "text": f"K線 {stock_id} monthly"}}
                            ]
                        },
                        {"type": "separator", "margin": "xs"},
                        {
                            "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                            "contents": [
                                {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id}"}},
                                {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily"}},
                                {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id}"}}
                            ]
                        },
                        {
                            "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                            "contents": [
                                {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id}"}},
                                {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id}"}}
                            ]
                        }
                    ]
                }
            }
        }

        line_payload = {
            "replyToken": reply_token,
            "messages": [chart_bubble, buttons_bubble]
        }
        return jsonify(line_payload), 200

    except Exception as e:
        print(f"💥 K線圖生成失敗：{str(e)}")
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# 🛠️ 路由 3：【千張大股東籌碼中心】(修復 500 錯誤完整版)
# -------------------------------------------------------------------------
@app.route('/get_holders', methods=['POST'])
def get_holders():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        reply_token = req_data.get('replyToken', '').strip()
        
        stock_id = re.sub(r'[^0-9]', '', raw_id.replace("持股", ""))[:10]
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")

        fm_token = os.environ.get("FINMIND_TOKEN", "")
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockShareholding", "data_id": stock_id, "token": fm_token}
        resp = requests.get(url, params=params).json()
        
        has_data = False
        table_rows = [
            {
                "type": "box", "layout": "horizontal", "backgroundColor": "#f2f2f2", "padding": "xs",
                "contents": [
                    {"type": "text", "text": "日期", "weight": "bold", "size": "xs", "align": "center"},
                    {"type": "text", "text": "大股東比", "weight": "bold", "size": "xs", "align": "center"},
                    {"type": "text", "text": "增減", "weight": "bold", "size": "xs", "align": "center"},
                    {"type": "text", "text": "人數", "weight": "bold", "size": "xs", "align": "center"}
                ]
            },
            {"type": "separator"}
        ]

        if resp.get("status") == 200 and resp.get("data"):
            df = pd.DataFrame(resp["data"])
            df_1000 = df[df["shareholding_class"].astype(str).str.contains("1000|1,000")].copy()
            
            if not df_1000.empty:
                df_1000 = df_1000.sort_values("date", ascending=False)
                if len(df_1000) > 1:
                    df_1000['diff'] = df_1000['proportions'].diff(-1)
                else:
                    df_1000['diff'] = 0.0
                    
                df_4 = df_1000.head(4).copy()
                has_data = True

                for _, row in df_4.iterrows():
                    raw_date = str(row.get("date", "----"))
                    date_str = raw_date[5:].replace("-", "/") if len(raw_date) >= 10 else raw_date
                    ratio_str = f"{row.get('proportions', 0.0):.2f}%"
                    
                    diff_val = row.get('diff', 0.0)
                    if pd.isna(diff_val):
                        diff_str, diff_color = "--", "#000000"
                    else:
                        diff_str = f"+{diff_val:.2f}%" if diff_val >= 0 else f"{diff_val:.2f}%"
                        diff_color = "#ff0000" if diff_val >= 0 else "#008000"
                        
                    count_str = f"{int(row.get('number_of_shareholders', 0)):,}人"

                    table_rows.append({
                        "type": "box", "layout": "horizontal", "padding": "xs",
                        "contents": [
                            {"type": "text", "text": date_str, "size": "xs", "align": "center"},
                            {"type": "text", "text": ratio_str, "size": "xs", "align": "center", "weight": "bold"},
                            {"type": "text", "text": diff_str, "size": "xs", "align": "center", "color": diff_color, "weight": "bold"},
                            {"type": "text", "text": count_str, "size": "xs", "align": "center"}
                        ]
                    })
                    table_rows.append({"type": "separator", "color": "#eeeeee"})

        if not has_data:
            table_rows.append({
                "type": "box", "layout": "horizontal", "padding": "md",
                "contents": [{"type": "text", "text": "⚠️ 暫無大股東歷史籌碼資料", "align": "center", "color": "#ff0000"}]
            })

        body_contents = [
            {"type": "text", "text": f"📊 {stock_name} ({stock_id})", "weight": "bold", "size": "lg"},
            {"type": "text", "text": "條件：大股東張數大於1000張歷史變動", "size": "xs", "color": "#888888", "margin": "xs"},
            {"type": "box", "layout": "vertical", "margin": "md", "spacing": "xs", "contents": table_rows},
            {"type": "separator"},
            {
                "type": "box", "layout": "horizontal", "spacing": "xs",
                "contents": [
                    {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id}"}},
                    {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily"}},
                    {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id}"}}
                ]
            },
            {
                "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                "contents": [
                    {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id}"}},
                    {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id}"}}
                ]
            }
        ]

        # 🚀 籌碼中心也統一打包成標準規格回傳
        line_payload = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "flex",
                    "altText": f"{stock_name} ({stock_id}) 大股東籌碼查詢結果",
                    "contents": {
                        "type": "bubble",
                        "body": {
                            "type": "box",
                            "layout": "vertical",
                            "spacing": "sm",
                            "contents": body_contents
                        }
                    }
                }
            ]
        }
        return jsonify(line_payload), 200

    except Exception as e:
        print(f"💥 籌碼系統發生錯誤：{str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
