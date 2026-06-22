import os
import io
import base64
import requests
from flask import Flask, request, jsonify
import yfinance as yf
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  # 確保在雲端伺服器（無顯示器環境）下畫圖不會崩潰
import matplotlib.pyplot as plt

app = Flask(__name__)

@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        # 1. 接收 Make.com 傳來的參數
        req_data = request.get_json() or {}
        stock_id = req_data.get('stock_id', '').strip()
        action_data = req_data.get('data', '').strip()

        if not stock_id:
            return jsonify({"status": "error", "message": "Missing stock_id"}), 200

        # 2. 判斷使用者是要看什麼時段的 K 線 (預設為日線 1d)
        # yfinance 參數對應：period (資料範圍), interval (K線頻率)
        if action_data == '1m':
            period, interval, title_text = '1d', '1m', '1分鐘分K'
        elif action_data == '5m':
            period, interval, title_text = '1d', '5m', '5分鐘分K'
        elif action_data == 'weekly':
            period, interval, title_text = '1y', '1wk', '週K線'
        else:
            period, interval, title_text = '6mo', '1d', '日K線'


import yfinance as yf  # 確保是用 yfinance，而不是自己用 requests 爬網頁
import pandas as pd
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import mplfinance as mpf

# ... 你的 Flask 路由定義 ...

    try:
        # 1. 轉換台灣股市代號格式 (例如 2330 轉 2330.TW)
        yf_code = f"{stock_id}.TW"
        
        # 2. 用 yfinance 抓取歷史數字資料 (避開網頁互動圖表抓不到的問題)
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period="60d", interval="1d") # 抓取近 60 天日線
        
        # 🚨 【防空警報 1】檢查有沒有抓到 Yahoo 資料
        if df.empty:
            print(f"❌ 錯誤：Yahoo Finance 找不到代號 {yf_code} 的資料！")
            return jsonify({
                "status": "error",
                "flex_contents": {
                    "type": "bubble",
                    "body": {
                        "type": "box", "layout": "vertical",
                        "contents": [{"type": "text", "text": f"找不到股票代號 {stock_id}，請確認是否輸入正確。", "color": "#ff0000"}]
                    }
                }
            }), 200

        stock_name = ticker.info.get('longName', stock_id) # 拿不到英文/中文全名就用代號代替

        # 3. 計算即時價格 (假設 df 裡面有資料了)
        latest_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
        change = latest_close - prev_close
        change_percent = (change / prev_close) * 100
        
        price_string = f"{latest_close:,.2f}"
        change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({'' if change >= 0 else ''}{change_percent:.2f}%)"
        color_theme = "#ff0000" if change >= 0 else "#008000" # 台灣紅漲綠跌

        # 4. 繪製 K 線圖
        buf = io.BytesIO()
        fig, axes = mpf.plot(
            df, type='candle', volume=True, returnfig=True, figsize=(8, 5),
            style='charles' # 使用標準查爾斯風格
        )
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close(fig)

        # 5. 上傳圖片到 ImgBB
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        img_api_key = os.environ.get("IMGBB_API_KEY")
        
        img_resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": img_api_key, "image": img_base64}
        )
        
        img_json = img_resp.json()
        
        # 🚨 【防空警報 2】檢查 ImgBB 是否真的成功吐回網址
        if img_resp.status_code != 200 or 'data' not in img_json:
            print(f"❌ 錯誤：ImgBB 上傳失敗！回應：{img_json}")
            # 如果圖片爆了，我們「改吐純文字版 Flex」，確保 Make 不會因為找不到欄位而死當
            return jsonify({
                "status": "success",
                "flex_contents": {
                    "type": "bubble",
                    "body": {
                        "type": "box", "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": f"{stock_name} ({stock_id})", "weight": "bold", "size": "lg"},
                            {"type": "text", "text": f"最新報價：{price_string} (圖表生成失敗)", "margin": "md"}
                        ]
                    }
                }
            }), 200

        # 如果都成功，拿到乾淨網址
        final_image_url = img_json['data'].get('display_url', img_json['data'].get('url'))

        # 6. 組裝成功的完整 K 線圖 Flex Message
        flex_contents = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": str(final_image_url).strip(),
                "size": "full", "aspectMode": "cover", "aspectRatio": "20:13"
            },
            "body": {
                "type": "box", "layout": "vertical",
                "contents": [
                    {"type": "text", "text": f"{str(stock_name)} ({str(stock_id)})", "weight": "bold", "size": "lg"},
                    {
                        "type": "box", "layout": "horizontal", "margin": "md",
                        "contents": [
                            {"type": "text", "text": f"最新價: {price_string}", "size": "sm", "weight": "bold"},
                            {"type": "text", "text": f"漲跌: {change_string}", "size": "sm", "align": "right", "color": color_theme}
                        ]
                    }
                ]
            }
        }

        return jsonify({"status": "success", "flex_contents": flex_contents}), 200

    except Exception as e:
        print(f"💥 系統嚴重崩潰：{str(e)}")
        return jsonify({"status": "error", "message": "伺服器內部錯誤"}), 200
