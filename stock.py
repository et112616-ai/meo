import os
import io
import requests
import pandas as pd
from flask import Flask, request, jsonify, send_file
import yfinance as yf
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  # 確保無顯示器 Linux 環境不崩潰
import matplotlib.pyplot as plt

app = Flask(__name__)

# 🌟 記憶體圖片快取（給 K 線圖直連使用）
IMAGE_CACHE = {}

# 🌟 台股精準中文名稱對照導航庫
STOCK_NAME_MAP = {
    "1101": "台泥", "2022": "聚亨", "2301": "光寶科", "2303": "聯電",
    "2313": "華通", "2330": "台積電", "2337": "旺宏", "2634": "漢翔",
    "4979": "華星光", "0052": "富邦科技", "009816": "凱基台灣TOP50"
}

# -------------------------------------------------------------------------
# 🛠️ 路由 1：圖片伺服器
# -------------------------------------------------------------------------
@app.route('/images/<image_key>.png', methods=['GET'])
def serve_image(image_key):
    img_bytes = IMAGE_CACHE.get(image_key)
    if img_bytes:
        return send_file(io.BytesIO(img_bytes), mimetype='image/png')
    return "Image not found", 404


# -------------------------------------------------------------------------
# 🛠️ 路由 2：【K線圖主控中心】修復 JSON 破裂地雷版
# -------------------------------------------------------------------------
@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        action_data = req_data.get('data', '').strip()

        stock_id = raw_id.replace("K線", "").replace("即時", "").strip().split()[0]
        if not stock_id:
            return jsonify({"status": "error", "message": "Missing stock_id"}), 200

        if '1m' in action_data:
            period, interval, title_text = '1d', '1m', '1 Min K-Line'
        elif '3m' in action_data:
            period, interval, title_text = '1d', '3m', '3 Min K-Line'
        elif '5m' in action_data:
            period, interval, title_text = '1d', '5m', '5 Min K-Line'
        elif '30m' in action_data:
            period, interval, title_text = '5d', '30m', '30 Min K-Line'
        elif 'weekly' in action_data:
            period, interval, title_text = '1y', '1wk', 'Weekly K-Line'
        elif 'monthly' in action_data:
            period, interval, title_text = '5y', '1mo', 'Monthly K-Line'
        else:
            period, interval, title_text = '3mo', '1d', 'Daily K-Line'

        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")

        yf_code = f"{stock_id}.TW"
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty or len(df) < 2:
            return jsonify({
                "status": "success",
                "flex_contents": {
                    "type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"{stock_name} 查無足夠 K 線資料。"}]}
                }
            }), 200

        latest_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
        change = latest_close - prev_close
        change_percent = (change / prev_close) * 100
        
        price_string = f"{latest_close:,.2f}"
        change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({'' if change >= 0 else ''}{change_percent:.2f}%)"
        color_theme = "#ff0000" if change >= 0 else "#008000"

        buf = io.BytesIO()
        fig, axes = mpf.plot(df, type='candle', volume=True, returnfig=True, figsize=(10, 6), style='yahoo')
        axes[0].set_title(f"STOCK: {stock_id} ({title_text})", fontsize=14, color='black')
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100, facecolor='white')
        
        image_key = f"chart_{stock_id}"
        IMAGE_CACHE[image_key] = buf.getvalue()
        buf.seek(0)
        plt.close('all')

        base_url = "https://meo-qput.onrender.com"
        final_image_url = f"{base_url}/images/{image_key}.png"

        # 🌟 終極修正：將網址轉為純粹乾淨的字串，阻絕任何 JSON 變形
        clean_img_url = str(final_image_url).strip()

        flex_contents = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "md",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "alignment": "center",
                        "contents": [
                            {"type": "text", "text": f"{stock_name} ({stock_id})", "weight": "bold", "size": "xl", "flex": 3, "gravity": "center"},
                            {"type": "button", "style": "secondary", "height": "sm", "flex": 1, "action": {"type": "message", "label": "期貨", "text": f"期貨 {stock_id}"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "1分", "text": f"K線 {stock_id} 1m"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "3分", "text": f"K線 {stock_id} 3m"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "5分", "text": f"K線 {stock_id} 5m"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "30分", "text": f"K線 {stock_id} 30m"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "日", "text": f"K線 {stock_id} daily"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "週", "text": f"K線 {stock_id} weekly"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "月", "text": f"K線 {stock_id} monthly"}}
                        ]
                    },
                    {"type": "separator"},
                    {
                        "type": "box", "layout": "vertical",
                        "contents": [
                            {"type": "image", "url": clean_img_url, "size": "full", "aspectMode": "cover", "aspectRatio": "20:13"},
                            {
                                "type": "box", "layout": "horizontal", "margin": "md",
                                "contents": [
                                    {"type": "text", "text": f"最新價: {price_string}", "weight": "bold", "size": "sm"},
                                    {"type": "text", "text": f"漲跌: {change_string}", "weight": "bold", "size": "sm", "color": color_theme, "align": "end"}
                                ]
                            }
                        ]
                    },
                    {"type": "separator"},
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id}"}}
                        ]
                    }
                ]
            }
        }
        return jsonify({"status": "success", "flex_contents": flex_contents}), 200

    except Exception as e:
        print(f"💥 K線主控系統崩潰：{str(e)}")
        return jsonify({"status": "error", "message": f"Server Error: {str(e)}"}), 200


# -------------------------------------------------------------------------
# 🛠️ 路由 3：【千張大股東籌碼中心】
# -------------------------------------------------------------------------
@app.route('/get_holders', methods=['POST'])
def get_holders():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        
        stock_id = raw_id.replace("持股", "").strip().split()[0]
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")

        fm_token = os.environ.get("FINMIND_TOKEN", "")
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockShareholding", "data_id": stock_id, "token": fm_token}
        resp = requests.get(url, params=params).json()
        
        if resp.get("status") != 200 or not resp.get("data") or len(resp["data"]) == 0:
            return jsonify({"status": "success", "flex_contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"⚠️ 暫無 {stock_name}({stock_id}) 的大股東籌碼資料，請稍後再試。"}]}}}), 200
            
        df = pd.DataFrame(resp["data"])
        df_1000 = df[df["shareholding_class"] == "1000以上"].copy()
        
        if df_1000.empty:
            classes = df["shareholding_class"].unique()
            if len(classes) > 0:
                df_1000 = df[df["shareholding_class"] == classes[-1]].copy()
            else:
                return jsonify({"status": "success", "flex_contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"⚠️ {stock_name} 的大股東資料格式不符。"}]}}}), 200

        df_1000 = df_1000.sort_values("date", ascending=False)
        
        if len(df_1000) > 1:
            df_1000['diff'] = df_1000['proportions'].diff(-1)
        else:
            df_1000['diff'] = 0.0
            
        df_4 = df_1000.head(4).copy()

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

        for _, row in df_4.iterrows():
            raw_date = str(row.get("date", "----"))
            date_str = raw_date[5:].replace("-", "/") if len(raw_date) >= 10 else raw_date
            
            proportions_val = row.get("proportions", 0.0)
            ratio_str = f"{proportions_val:.2f}%"
            
            diff_val = row.get('diff', 0.0)
            if pd.isna(diff_val):
                diff_str, diff_color = "--", "#000000"
            else:
                diff_str = f"+{diff_val:.2f}%" if diff_val >= 0 else f"{diff_val:.2f}%"
                diff_color = "#ff0000" if diff_val >= 0 else "#008000"
                
            shareholders_val = row.get("number_of_shareholders", 0)
            count_str = f"{int(shareholders_val):,}人"

            row_block = {
                "type": "box", "layout": "horizontal", "padding": "xs",
                "contents": [
                    {"type": "text", "text": date_str, "size": "xs", "align": "center"},
                    {"type": "text", "text": ratio_str, "size": "xs", "align": "center", "weight": "bold"},
                    {"type": "text", "text": diff_str, "size": "xs", "align": "center", "color": diff_color, "weight": "bold"},
                    {"type": "text", "text": count_str, "size": "xs", "align": "center"}
                ]
            }
            table_rows.append(row_block)
            table_rows.append({"type": "separator", "color": "#eeeeee"})

        flex_contents = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"📊 {stock_name} ({stock_id})", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": "條件：大股東張數大於1000張變動", "size": "xs", "color": "#888888", "margin": "xs"},
                    {"type": "box", "layout": "vertical", "margin": "md", "spacing": "xs", "contents": table_rows},
                    {"type": "separator", "margin": "lg"},
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "md",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id}"}}
                        ]
                    }
                ]
            }
        }
        return jsonify({"status": "success", "flex_contents": flex_contents}), 200

    except Exception as e:
        print(f"💥 籌碼系統發生錯誤：{str(e)}")
        return jsonify({"status": "error", "message": f"籌碼中心故障: {str(e)}"}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
