import os
import io
import requests
import json
import re
import pandas as pd
from flask import Flask, request, jsonify, send_file, Response
import yfinance as yf
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import twstock

app = Flask(__name__)

# ==========================================
# 🌟 核心升級 1：證交所全自動連線初始化邏輯
# ==========================================
print("⏳ 正在連線台灣證交所下載最新個股清單...")
try:
    # 強制 twstock 更新股票代碼清單
    twstock.__update_codes()
    
    # 建立動態股票對照表（包含上市與上櫃）
    STOCK_NAME_MAP = {}
    for code, info in twstock.codes.items():
        # 過濾掉權證、衍生商品，只留下純股票、ETF等主要標的
        if info.type in ['股票', 'ETF', '台灣存託憑證(TDR)', '受益證券']:
            STOCK_NAME_MAP[code] = info.name
            
    print(f"🎉 證交所資料同步成功！已自動載入 {len(STOCK_NAME_MAP)} 檔台股/ETF 繁體中文名稱。")
except Exception as e:
    print(f"⚠️ 證交所連線失敗，啟用預設內嵌核心持股名單。錯誤: {str(e)}")
    # 備用核心持股清單（防止沒網路時專案崩潰）
    STOCK_NAME_MAP = {
        "1101": "台泥", "2022": "聚亨", "2301": "光寶科", "2303": "聯電",
        "2313": "華通", "2330": "台積電", "2337": "旺宏", "2634": "漢翔",
        "4979": "華星光", "0052": "富邦科技", "009816": "凱基台灣TOP50"
    }

# ==========================================
# 🌟 核心升級 2：Matplotlib 繁體中文支援中心
# ==========================================
def setup_chinese_font():
    try:
        system_fonts = [f.name for f in fm.fontManager.ttflist]
        fallback_fonts = ['Noto Sans CJK JP', 'Noto Sans CJK KR', 'Noto Sans CJK SC', 'Noto Sans CJK TC', 'Droid Sans Fallback']
        
        chosen_font = None
        for font in fallback_fonts:
            if font in system_fonts:
                chosen_font = font
                break
                
        if chosen_font:
            matplotlib.rc('font', family=chosen_font)
            plt.rcParams['axes.unicode_minus'] = False
            print(f"🎉 成功啟用系統中文字體：{chosen_font}")
            return

        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTC/NotoSansCJK-Regular.ttc"
        font_path = os.path.join(os.getcwd(), "NotoSansCJK-Regular.ttc")
        
        if not os.path.exists(font_path):
            print("⏳ 雲端環境查無中文字體，正在線上下載思源黑體 (約需 5-10 秒)...")
            r = requests.get(font_url, stream=True)
            if r.status_code == 200:
                with open(font_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        if chunk: f.write(chunk)
                print("✅ 字體下載完成！")
            else:
                print("❌ 字體下載失敗，將維持預設英文顯示。")
                return

        if os.path.exists(font_path):
            font_prop = fm.FontProperties(fname=font_path)
            matplotlib.rc('font', family=font_prop.get_name())
            fm.fontManager.addfont(font_path)
            plt.rcParams['axes.unicode_minus'] = False
            print(f"🎉 成功動態載入中文字體：{font_prop.get_name()}")
            
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

        stock_id = re.sub(r'[^a-zA-Z0-9]', '', raw_id.replace("K線", "").replace("即時", ""))[:10]
        if not stock_id:
            return jsonify({"status": "error", "message": "Missing stock_id"}), 200

        if '1m' in action_data:
            period, interval, title_text = '1d', '1m', '1分鐘K線'
        elif '3m' in action_data:
            period, interval, title_text = '1d', '3m', '3分鐘K線'
        elif '5m' in action_data:
            period, interval, title_text = '1d', '5m', '5分鐘K線'
        elif '30m' in action_data:
            period, interval, title_text = '5d', '30m', '30分鐘K線'
        elif 'weekly' in action_data:
            period, interval, title_text = '1y', '1wk', '週K線'
        elif 'monthly' in action_data:
            period, interval, title_text = '5y', '1mo', '月K線'
        else:
            period, interval, title_text = '3mo', '1d', '日K線'

        # 這裡會自動去動態字典裡抓名字，查不到則顯示個股代號
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")

        yf_code = f"{stock_id}.TW"
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty or len(df) < 2:
            flex_contents = {
                "type": "bubble", 
                "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"{stock_name} 查無足夠 K 線資料。"}]}
            }
            line_flex_message = {
                "type": "flex",
                "altText": f"{stock_name} ({stock_id}) 查無資料",
                "contents": flex_contents
            }
            return jsonify({"status": "success", "line_message": line_flex_message}), 200

        latest_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
        change = latest_close - prev_close
        change_percent = (change / prev_close) * 100
        
        price_string = f"{latest_close:,.2f}"
        change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({change_percent:.2f}%)"
        color_theme = "#ff0000" if change >= 0 else "#008000"

        image_key = f"chart_{stock_id}"
        fig, axes = mpf.plot(df, type='candle', volume=True, returnfig=True, figsize=(10, 6), style='yahoo')
        axes[0].set_title(f"{stock_name} ({stock_id}) - {title_text}", fontsize=16, color='black', weight='bold')
        fig.savefig(f"{image_key}.png", format='png', bbox_inches='tight', dpi=100, facecolor='white')
        plt.close('all')

        base_url = "https://meo-qput.onrender.com"
        final_image_url = f"{base_url}/images/{image_key}.png"

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
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "30分", "text": f"K線 {stock_id} 30m"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs", "margin": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "日", "text": f"K線 {stock_id} daily"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "週", "text": f"K線 {stock_id} weekly"}},
                            {"type": "button", "height": "sm", "style": "link", "action": {"type": "message", "label": "月", "text": f"K線 {stock_id} monthly"}}
                        ]
                    },
                    {"type": "separator"},
                    {
                        "type": "box", "layout": "vertical",
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
                    },
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
            }
        }
        
        line_flex_message = {
            "type": "flex",
            "altText": f"{stock_name} ({stock_id}) K線圖查詢結果",
            "contents": flex_contents
        }
        return jsonify({"status": "success", "line_message": line_flex_message}), 200

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
        
        stock_id = re.sub(r'[^0-9]', '', raw_id.replace("持股", ""))[:10]
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")

        fm_token = os.environ.get("FINMIND_TOKEN", "")
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockShareholding", "data_id": stock_id, "token": fm_token}
        resp = requests.get(url, params=params).json()
        
        if resp.get("status") != 200 or not resp.get("data") or len(resp["data"]) == 0:
            flex_contents = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"⚠️ 暫無 {stock_name}({stock_id}) 的大股東籌碼資料，請稍後再試。"}]}}
            line_flex_message = {
                "type": "flex",
                "altText": f"{stock_name} ({stock_id}) 大股東籌碼查詢結果",
                "contents": flex_contents
            }
            return jsonify({"status": "success", "line_message": line_flex_message}), 200

        df = pd.DataFrame(resp["data"])
        df_1000 = df[df["shareholding_class"] == "1000以上"].copy()
        
        if df_1000.empty:
            classes = df["shareholding_class"].unique()
            if len(classes) > 0:
                df_1000 = df[df["shareholding_class"] == classes[-1]].copy()
            else:
                flex_contents = {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": f"⚠️ {stock_name} 的大股東資料格式不符。"}]}}
                line_flex_message = {
                    "type": "flex",
                    "altText": f"{stock_name} ({stock_id}) 大股東籌碼查詢結果",
                    "contents": flex_contents
                }
                return jsonify({"status": "success", "line_message": line_flex_message}), 200

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
            }
        }
        
        line_flex_message = {
            "type": "flex",
            "altText": f"{stock_name} ({stock_id}) 大股東籌碼查詢結果",
            "contents": flex_contents
        }
        return jsonify({"status": "success", "line_message": line_flex_message}), 200

    except Exception as e:
        print(f"💥 籌碼系統發生錯誤：{str(e)}")
        return jsonify({"status": "error", "message": f"籌碼中心故障: {str(e)}"}), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
