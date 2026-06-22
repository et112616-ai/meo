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
        
      # 7. 組裝 LINE Flex Message 內容 (K線圖絕對通車、終極防護版)
        # 我們將圖片放在hero區，文字放在body區，移除所有複雜按鈕，只放文字按鈕，確保JSON乾淨。
        
        flex_contents = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{str(stock_name)} ({str(stock_id)})",
                        "weight": "bold",
                        "size": "lg"
                    },
                    {
                        "type": "text",
                        "text": f"最新報價：{str(price_string)}",
                        "size": "md",
                        "margin": "md"
                    },
                    {"type": "separator", "margin": "lg"}
                ]
            }
        }

        # [核心關鍵] 圖片區：如果 final_image_url 存在，且是乾淨的 https 網址，我們才加入。
        # 我們加入了 str() 強制轉型，防止 None 錯誤。
        if final_image_url:
            image_block = {
                "type": "image",
                "url": str(final_image_url).strip(), # strip() 移除可能導致JSON錯誤的空白
                "size": "full",
                "aspectMode": "cover", # 圖片裁切模式
                "aspectRatio": "20:13", # 完美適配手機版型
                "gravity": "center"
            }
            # 將圖片區設定為 Flex 的 Hero (圖片區)
            flex_contents["hero"] = image_block

        # 最後加入一個極簡的文字按鈕，防止空內容報錯 (使用最安全的 message action)
        footer_block = {
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": "查看更多新聞",
                        "text": f"新聞 {str(stock_id)}"
                    }
                }
            ],
            "margin": "lg"
        }
        flex_contents["body"]["contents"].append(footer_block)
        
        # 8. 成功回傳大禮包給 Make.com
        return jsonify({
            "status": "success",
            "image_url": final_image_url,
            "flex_contents": flex_contents
        }), 200

    except Exception as e:
        # 萬一程式內部有其他未預期錯誤，捕捉並回傳錯誤訊息，防止 Make.com 拿到乾白畫面
        return jsonify({"status": "error", "message": f"Server Error: {str(e)}"}), 200

if __name__ == '__main__':
    # Render 會自動指定 PORT 環境變數
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
