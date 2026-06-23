import os
import io
import requests
import json
import re
import datetime
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

# 秉璋的專屬自選股與名稱對應表
STOCK_NAME_MAP = {
    "1101": "台泥", "2022": "聚亨", "2301": "光寶科", "2303": "聯電",
    "2313": "華通", "2330": "台積電", "2337": "旺宏", "2634": "漢翔",
    "4979": "華星光", "0052": "富邦科技", "009816": "凱基台灣TOP50", "2404": "漢唐"
}

# 個股期貨英文代碼與盤態對應表 (全：代表支援夜盤，日：僅日盤)
FUTURE_MAP = {
    "2330": {"code": "CDF", "has_all": True},   # 台積電期貨 (全)
    "2303": {"code": "CCF", "has_all": True},   # 聯電期貨 (全)
    "2404": {"code": "WGO", "has_all": False},  # 漢唐期貨 (日)
    "2313": {"code": "GCO", "has_all": True},   # 華通期貨 (全)
    "2301": {"code": "DDF", "has_all": False},  # 光寶科期貨 (日)
    "3081": {"code": "OOF", "has_all": True},   # 聯亞期貨 (全)
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
# 📈 路由 1：【K線圖與即時主控中心】(支援中文輸入反向尋找)
# -------------------------------------------------------------------------
@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        action_data = req_data.get('data', '').strip()
        reply_token = req_data.get('replyToken', '').strip()

        # 🧠 鐵壁防呆判斷：先看是不是純數字
        digits_only = re.sub(r'[^0-9]', '', raw_id)
        
        if digits_only:
            # 1. 只要有抓到數字，它就是絕對的股票代號！
            stock_id = digits_only[:10]
        else:
            # 2. 完全沒有數字，才代表使用者輸入的是純中文（如：漢唐、台積電）
            stock_id = None
            clean_name = raw_id.replace("K線", "").replace("即時", "").replace("期貨", "").replace("現貨", "").replace("法人", "").replace("持股", "").replace("融資券", "").strip()
            for code, name in STOCK_NAME_MAP.items():
                if clean_name in name or name in clean_name:
                    stock_id = code
                    break
                    
        if not stock_id:
            return jsonify({"replyToken": reply_token, "is_text": True, "text": f"⚠️ 無法辨識股票代碼或中文名稱: {raw_id}"}), 200

        # 🧠 判斷目前是現貨還是期貨狀態
        is_future_state = False
        if "future" in action_data or "期貨" in raw_id:
            is_future_state = True
        if "spot" in action_data or "現貨" in raw_id:
            is_future_state = False

        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")
        
        # 解析 K 線週期
        if '1m' in action_data: period, interval, title_suffix = '1d', '1m', '1分鐘K線'
        elif '3m' in action_data: period, interval, title_suffix = '1d', '3m', '3分鐘K線'
        elif '5m' in action_data: period, interval, title_suffix = '1d', '5m', '5分鐘K線'
        elif '30m' in action_data: period, interval, title_suffix = '5d', '30m', '30分鐘K線'
        elif 'weekly' in action_data: period, interval, title_suffix = '1y', '1wk', '週K線'
        elif 'monthly' in action_data: period, interval, title_suffix = '5y', '1mo', '月K線'
        else: period, interval, title_suffix = '3mo', '1d', '日K線'

        # 資料獲取
        if not is_future_state:
            yf_code = f"{stock_id}.TW"
            df = yf.Ticker(yf_code).history(period=period, interval=interval)
            title_text = f"{stock_name} ({stock_id}) - {title_suffix}"
            
            if df.empty:
                return jsonify({"replyToken": reply_token, "is_text": True, "text": f"{stock_name} 查無現貨資料。"}), 200
                
            latest_close = df['Close'].iloc[-1]
            change = latest_close - df['Close'].iloc[-2] if len(df) > 1 else 0
            change_percent = (change / df['Close'].iloc[-2]) * 100 if len(df) > 1 else 0
            
            time_str = df.index[-1].strftime('%Y/%m/%d %H:%M:%S')
            price_string = f"{latest_close:,.2f}"
            change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({change_percent:.2f}%)"
        else:
            f_info = FUTURE_MAP.get(stock_id, {"code": f"{stock_id}F", "has_all": False})
            f_code = f_info["code"]
            pane_type = "全" if f_info["has_all"] else "日"
            title_text = f"【期貨】{stock_name} ({f_code} & {pane_type}) - {title_suffix}"
            
            # 期貨模擬數據對照
            yf_code = f"{stock_id}.TW"
            df = yf.Ticker(yf_code).history(period=period, interval=interval)
            
            if df.empty:
                return jsonify({"replyToken": reply_token, "is_text": True, "text": f"{stock_name} 期貨對應標的查無資料。"}), 200
                
            latest_close = df['Close'].iloc[-1]
            change = df['Close'].iloc[-1] - df['Close'].iloc[-2] if len(df) > 1 else 0
            change_percent = (change / df['Close'].iloc[-2]) * 100 if len(df) > 1 else 0
            
            time_str = datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S')
            price_string = f"{latest_close:,.0f}"
            change_string = f"{'+' if change >= 0 else ''}{change:.0f} ({change_percent:.2f}%)"

        color_theme = "#ff0000" if change >= 0 else "#008000"
        image_key = f"chart_{stock_id}_{'future' if is_future_state else 'spot'}"
        
        fig, axes = mpf.plot(df, type='candle', volume=True, returnfig=True, figsize=(10, 6), style='yahoo')
        axes[0].set_title(title_text, fontsize=14, color='black', weight='bold', **({'fontname': CHINESE_FONT_NAME} if CHINESE_FONT_NAME else {}))
        fig.savefig(f"{image_key}.png", format='png', bbox_inches='tight', dpi=100, facecolor='white')
        plt.close('all')

        base_url = "https://meo-qput.onrender.com"
        final_image_url = f"{base_url}/images/{image_key}.png"
        state_suffix = "future" if is_future_state else "spot"

        bubble_payload = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal",
                        "contents": [
                            {"type": "text", "text": f"📈 {stock_name} ({stock_id})", "weight": "bold", "size": "md"},
                            {"type": "text", "text": "期貨" if is_future_state else "現貨", "size": "xs", "color": "#ffffff", "backgroundColor": "#ff8c00" if is_future_state else "#0066cc", "align": "center", "gravity": "center", "flex": 0, "margin": "md"}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "none", "margin": "xs",
                        "contents": [
                            {"type": "text", "text": "1分", "size": "sm", "color": "#0066cc", "align": "center", "flex": 1, "action": {"type": "message", "text": f"K線 {stock_id} 1m {state_suffix}"}},
                            {"type": "text", "text": "3分", "size": "sm", "color": "#0066cc", "align": "center", "flex": 1, "action": {"type": "message", "text": f"K線 {stock_id} 3m {state_suffix}"}},
                            {"type": "text", "text": "5分", "size": "sm", "color": "#0066cc", "align": "center", "flex": 1, "action": {"type": "message", "text": f"K線 {stock_id} 5m {state_suffix}"}},
                            {"type": "text", "text": "日K", "size": "sm", "color": "#0066cc", "align": "center", "flex": 1, "action": {"type": "message", "text": f"K線 {stock_id} daily {state_suffix}"}},
                            {"type": "text", "text": "週K", "size": "sm", "color": "#0066cc", "align": "center", "flex": 1, "action": {"type": "message", "text": f"K線 {stock_id} weekly {state_suffix}"}},
                            {"type": "text", "text": "月K", "size": "sm", "color": "#0066cc", "align": "center", "flex": 1, "action": {"type": "message", "text": f"K線 {stock_id} monthly {state_suffix}"}}
                        ]
                    },
                    {"type": "separator", "margin": "xs"},
                    {"type": "image", "url": final_image_url, "size": "full", "aspectMode": "cover", "aspectRatio": "20:13"},
                    {"type": "separator", "margin": "xs"},
                    # 🌟 修正點：將最新價、漲跌與資料時間，全部安全地包在同一個垂直 Box 容器內，確保 LINE 絕對不爆框、拒收
                    {
                        "type": "box", "layout": "vertical", "margin": "xs", "spacing": "xs",
                        "contents": [
                            {
                                "type": "box", "layout": "horizontal",
                                "contents": [
                                    {"type": "text", "text": f"最新價: {price_string}", "weight": "bold", "size": "sm"},
                                    {"type": "text", "text": f"漲跌: {change_string}", "weight": "bold", "size": "sm", "color": color_theme, "align": "end"}
                                ]
                            },
                            {"type": "text", "text": f"資料時間：{time_str}", "size": "xs", "color": "#888888"}
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} {state_suffix}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily {state_suffix}"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id} spot"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "secondary" if is_future_state else "primary", 
                             "action": {"type": "message", "label": "期現貨" if is_future_state else "期貨", "text": f"K線 {stock_id} daily spot" if is_future_state else f"K線 {stock_id} daily future"}}
                        ]
                    }
                ]
            }
        }

        return jsonify({"replyToken": reply_token, "is_text": False, "altText": f"{stock_name} 雙態查詢結果", "bubble": bubble_payload}), 200

    except Exception as e:
        print(f"💥 主控中心系統錯誤：{str(e)}")
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# 📊 路由 2：【三大法人籌碼中心】(支援中文反向模糊查找)
# -------------------------------------------------------------------------
@app.route('/get_legal_deal', methods=['POST'])
def get_legal_deal():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        reply_token = req_data.get('replyToken', '').strip()
        
        # 🧠 鐵壁防呆判斷：先看是不是純數字
        digits_only = re.sub(r'[^0-9]', '', raw_id)
        
        if digits_only:
            # 1. 只要有抓到數字，它就是絕對的股票代號！
            stock_id = digits_only[:10]
        else:
            # 2. 完全沒有數字，才代表使用者輸入的是純中文（如：漢唐、台積電）
            stock_id = None
            clean_name = raw_id.replace("K線", "").replace("即時", "").replace("期貨", "").replace("現貨", "").replace("法人", "").replace("持股", "").replace("融資券", "").strip()
            for code, name in STOCK_NAME_MAP.items():
                if clean_name in name or name in clean_name:
                    stock_id = code
                    break
                    
        if not stock_id:
            return jsonify({"error": "Missing stock_id"}), 400
            
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")
        fm_token = os.environ.get("FINMIND_TOKEN", "")
        
        end_date = datetime.date.today().strftime('%Y-%m-%d')
        start_date = (datetime.date.today() - datetime.timedelta(days=90)).strftime('%Y-%m-%d')
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockInstitutionalInvestorsBuySell", "data_id": stock_id, "start_date": start_date, "end_date": end_date, "token": fm_token}
        resp = requests.get(url, params=params).json()

        image_key = f"legal_{stock_id}"
        has_chart = False
        latest_info_str = "暫無即時法人持股數據"

        if resp.get("status") == 200 and resp.get("data"):
            df = pd.DataFrame(resp["data"])
            if not df.empty and 'buy' in df.columns and 'sell' in df.columns:
                df['net'] = (df['buy'] - df['sell']) / 1000
                df['date'] = pd.to_datetime(df['date'])
                
                pivoted = df.pivot_table(index='date', columns='name', values='net', aggfunc='sum').fillna(0)
                pivoted = pivoted.sort_index().tail(60)
                
                if not pivoted.empty:
                    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True, facecolor='white')
                    target_legal = ['外資', '投信', '自營商']
                    
                    for i, name in enumerate(target_legal):
                        ax = axes[i]
                        if name in pivoted.columns:
                            series = pivoted[name]
                            pos_mask = series >= 0
                            neg_mask = series < 0
                            ax.bar(series.index[pos_mask], series[pos_mask], color='#ff4d4d', width=0.6)
                            ax.bar(series.index[neg_mask], series[neg_mask], color='#2ecc71', width=0.6)
                        ax.axhline(0, color='gray', linestyle='--', linewidth=0.8)
                        ax.set_ylabel(f"{name}\n(張)", fontsize=10, rotation=0, labelpad=20, **({'fontname': CHINESE_FONT_NAME} if CHINESE_FONT_NAME else {}))
                        ax.grid(True, linestyle=':', alpha=0.6)
                    
                    plt.xticks(rotation=15)
                    axes[0].set_title(f"{stock_name} ({stock_id}) 三大法人近三個月買賣超分布圖", fontsize=14, color='black', weight='bold', **({'fontname': CHINESE_FONT_NAME} if CHINESE_FONT_NAME else {}))
                    plt.tight_layout()
                    fig.savefig(f"{image_key}.png", format='png', bbox_inches='tight', dpi=100)
                    plt.close('all')
                    has_chart = True
                    
                    last_date = pivoted.index[-1].strftime('%m/%d')
                    latest_info_str = f"最新日期：{last_date} 外資:{pivoted['外資'].iloc[-1]:+,.0f}張 | 投信:{pivoted['投信'].iloc[-1]:+,.0f}張"

        if not has_chart:
            fig, ax = plt.subplots(figsize=(6, 2))
            ax.text(0.5, 0.5, "該股無足夠法人買賣超歷史數據", ha='center', va='center', fontsize=12, **({'fontname': CHINESE_FONT_NAME} if CHINESE_FONT_NAME else {}))
            fig.savefig(f"{image_key}.png", format='png')
            plt.close('all')

        base_url = "https://meo-qput.onrender.com"
        final_image_url = f"{base_url}/images/{image_key}.png"

        bubble_payload = {
            "type": "bubble",
            "body": {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": [
                    {"type": "text", "text": f"📊 {stock_name} ({stock_id}) 法人籌碼趨勢", "weight": "bold", "size": "md"},
                    {"type": "text", "text": latest_info_str, "size": "xs", "color": "#e67e22", "weight": "bold"},
                    {"type": "separator", "margin": "xs"},
                    {"type": "image", "url": final_image_url, "size": "full", "aspectMode": "cover", "aspectRatio": "10:8"},
                    {"type": "separator", "margin": "xs"}
                ]
            },
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id} spot"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "期貨", "text": f"K線 {stock_id} daily future"}}
                        ]
                    }
                ]
            }
        }

        return jsonify({"replyToken": reply_token, "is_text": False, "bubble": bubble_payload}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# 🏛️ 路由 3：【大股東持股明細】(支援中文反向模糊查找)
# -------------------------------------------------------------------------
@app.route('/get_holders', methods=['POST'])
def get_holders():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        reply_token = req_data.get('replyToken', '').strip()
        
        # 🧠 鐵壁防呆判斷：先看是不是純數字
        digits_only = re.sub(r'[^0-9]', '', raw_id)
        
        if digits_only:
            # 1. 只要有抓到數字，它就是絕對的股票代號！
            stock_id = digits_only[:10]
        else:
            # 2. 完全沒有數字，才代表使用者輸入的是純中文（如：漢唐、台積電）
            stock_id = None
            clean_name = raw_id.replace("K線", "").replace("即時", "").replace("期貨", "").replace("現貨", "").replace("法人", "").replace("持股", "").replace("融資券", "").strip()
            for code, name in STOCK_NAME_MAP.items():
                if clean_name in name or name in clean_name:
                    stock_id = code
                    break
                    
        if not stock_id:
            return jsonify({"error": "Missing stock_id"}), 400
            
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")
        fm_token = os.environ.get("FINMIND_TOKEN", "")
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockShareholding", "data_id": stock_id, "token": fm_token}
        resp = requests.get(url, params=params).json()
        
        body_contents = [
            {"type": "text", "text": f"🏛️ {stock_name} ({stock_id}) 大股東持股", "weight": "bold", "size": "md"},
            {"type": "text", "text": "級距：持股 1000 張以上大戶每週變動趨勢", "size": "xs", "color": "#888888"},
            {"type": "separator", "margin": "sm"},
            {
                "type": "box", "layout": "horizontal", "backgroundColor": "#f2f2f2", "margin": "xs",
                "contents": [
                    {"type": "text", "text": "日期", "weight": "bold", "size": "xs", "align": "center", "flex": 15, "wrap": False},
                    {"type": "text", "text": "大股東比", "weight": "bold", "size": "xs", "align": "center", "flex": 25, "wrap": False},
                    {"type": "text", "text": "大股東變動", "weight": "bold", "size": "xs", "align": "center", "flex": 25, "wrap": False},
                    {"type": "text", "text": "大股東人數", "weight": "bold", "size": "xs", "align": "center", "flex": 25, "wrap": False}
                ]
            },
            {"type": "separator", "color": "#dddddd"}
        ]

        has_data = False
        if resp.get("status") == 200 and resp.get("data"):
            df = pd.DataFrame(resp["data"])
            df_1000 = df[df["shareholding_class"].astype(str).str.contains("1000|1,000")].copy()
            
            if not df_1000.empty:
                df_1000 = df_1000.sort_values("date", ascending=False)
                df_1000['diff'] = df_1000['proportions'].diff(-1) if len(df_1000) > 1 else 0.0
                
                df_6 = df_1000.head(6).copy()
                has_data = True

                for _, row in df_6.iterrows():
                    raw_date = str(row.get("date", "----"))
                    date_str = raw_date[5:].replace("-", "/") if len(raw_date) >= 10 else raw_date
                    ratio_str = f"{row.get('proportions', 0.0):.2f}%"
                    
                    diff_val = row.get('diff', 0.0)
                    diff_str = f"+{diff_val:.2f}%" if diff_val >= 0 else f"{diff_val:.2f}%"
                    diff_color = "#ff0000" if diff_val >= 0 else "#008000"
                    count_str = f"{int(row.get('number_of_shareholders', 0))}人"

                    body_contents.append({
                        "type": "box", "layout": "horizontal", "margin": "xs",
                        "contents": [
                            {"type": "text", "text": date_str, "size": "xs", "align": "center", "flex": 15, "wrap": False},
                            {"type": "text", "text": ratio_str, "size": "xs", "align": "center", "weight": "bold", "flex": 25, "wrap": False},
                            {"type": "text", "text": diff_str, "size": "xs", "align": "center", "color": diff_color, "weight": "bold", "flex": 25, "wrap": False},
                            {"type": "text", "text": count_str, "size": "xs", "align": "center", "flex": 25, "wrap": False}
                        ]
                    })
                    body_contents.append({"type": "separator", "color": "#eeeeee", "margin": "xs"})

        bubble_payload = {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "spacing": "xs", "contents": body_contents},
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id} spot"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "期貨", "text": f"K線 {stock_id} daily future"}}
                        ]
                    }
                ]
            }
        }

        return jsonify({"replyToken": reply_token, "is_text": False, "bubble": bubble_payload}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# 📉 路由 4：【融資券信用交易中心】(支援中文反向模糊查找)
# -------------------------------------------------------------------------
@app.route('/get_margin', methods=['POST'])
def get_margin():
    try:
        req_data = request.get_json() or {}
        raw_id = req_data.get('stock_id', '').strip()
        reply_token = req_data.get('replyToken', '').strip()
        
        # 🧠 鐵壁防呆判斷：先看是不是純數字
        digits_only = re.sub(r'[^0-9]', '', raw_id)
        
        if digits_only:
            # 1. 只要有抓到數字，它就是絕對的股票代號！
            stock_id = digits_only[:10]
        else:
            # 2. 完全沒有數字，才代表使用者輸入的是純中文（如：漢唐、台積電）
            stock_id = None
            clean_name = raw_id.replace("K線", "").replace("即時", "").replace("期貨", "").replace("現貨", "").replace("法人", "").replace("持股", "").replace("融資券", "").strip()
            for code, name in STOCK_NAME_MAP.items():
                if clean_name in name or name in clean_name:
                    stock_id = code
                    break
                    
        if not stock_id:
            return jsonify({"error": "Missing stock_id"}), 400
            
        stock_name = STOCK_NAME_MAP.get(stock_id, f"個股 {stock_id}")
        fm_token = os.environ.get("FINMIND_TOKEN", "")
        
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {"dataset": "TaiwanStockMarginPurchaseShortSale", "data_id": stock_id, "token": fm_token}
        resp = requests.get(url, params=params).json()
        
        body_contents = [
            {"type": "text", "text": f"📉 {stock_name} ({stock_id}) 融資券信用交易", "weight": "bold", "size": "md"},
            {"type": "separator", "margin": "sm"},
            {
                "type": "box", "layout": "horizontal", "backgroundColor": "#f2f2f2", "margin": "xs",
                "contents": [
                    {"type": "text", "text": "日期", "weight": "bold", "size": "xs", "align": "center", "flex": 18, "wrap": False},
                    {"type": "text", "text": "融資餘額", "weight": "bold", "size": "xs", "align": "center", "flex": 28, "wrap": False},
                    {"type": "text", "text": "融券餘額", "weight": "bold", "size": "xs", "align": "center", "flex": 26, "wrap": False},
                    {"type": "text", "text": "資券比", "weight": "bold", "size": "xs", "align": "center", "flex": 28, "wrap": False}
                ]
            },
            {"type": "separator", "color": "#dddddd"}
        ]

        if resp.get("status") == 200 and resp.get("data"):
            df = pd.DataFrame(resp["data"])
            if not df.empty:
                df = df.sort_values("date", ascending=False)
                df_6 = df.head(6)
                
                for _, row in df_6.iterrows():
                    raw_date = str(row.get("date", "----"))
                    date_str = raw_date[5:].replace("-", "/") if len(raw_date) >= 10 else raw_date
                    
                    margin_rem = row.get("MarginRemaining", 0)
                    short_rem = row.get("ShortRemaining", 0)
                    ratio_val = (short_rem / margin_rem * 100) if margin_rem > 0 else 0.0
                    
                    margin_str = f"{margin_rem:,}"
                    short_str = f"{short_rem:,}"
                    ratio_str = f"{ratio_val:.2f}%"

                    body_contents.append({
                        "type": "box", "layout": "horizontal", "margin": "xs",
                        "contents": [
                            {"type": "text", "text": date_str, "size": "xs", "align": "center", "flex": 18, "wrap": False},
                            {"type": "text", "text": margin_str, "size": "xs", "align": "center", "flex": 28, "wrap": False},
                            {"type": "text", "text": short_str, "size": "xs", "align": "center", "flex": 26, "wrap": False},
                            {"type": "text", "text": ratio_str, "size": "xs", "align": "center", "weight": "bold", "color": "#e67e22", "flex": 28, "wrap": False}
                        ]
                    })
                    body_contents.append({"type": "separator", "color": "#eeeeee", "margin": "xs"})

        bubble_payload = {
            "type": "bubble",
            "body": {"type": "box", "layout": "vertical", "spacing": "xs", "contents": body_contents},
            "footer": {
                "type": "box", "layout": "vertical", "spacing": "xs",
                "contents": [
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "即時", "text": f"即時 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "K線", "text": f"K線 {stock_id} daily spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "法人", "text": f"法人 {stock_id} spot"}}
                        ]
                    },
                    {
                        "type": "box", "layout": "horizontal", "spacing": "xs",
                        "contents": [
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "持股", "text": f"持股 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "融資券", "text": f"融資券 {stock_id} spot"}},
                            {"type": "button", "height": "sm", "style": "primary", "action": {"type": "message", "label": "期貨", "text": f"K線 {stock_id} daily future"}}
                        ]
                    }
                ]
            }
        }

        return jsonify({"replyToken": reply_token, "is_text": False, "bubble": bubble_payload}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
