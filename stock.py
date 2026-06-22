import os
import io
import base64
import requests
import pandas as pd
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

        # 2. 判斷使用者是要看什麼時段的 K 線 (預設為日線)
        # yfinance 參數對應：period (資料範圍), interval (K線頻率)
        if action_data == '1m':
            period, interval, title_text = '1d', '1m', '1分鐘分K'
        elif action_data == '5m':
            period, interval, title_text = '1d', '5m', '5分鐘分K'
        elif action_data == 'weekly':
            period, interval, title_text = '1y', '1wk', '週K線'
        else:
            period, interval, title_text = '6mo', '1d', '日K線'

        # 3. 轉換台灣股市代號格式 (例如 2330 轉 2330.TW)
        yf_code = f"{stock_id}.TW"
        
        # 4. 用 yfinance 抓取歷史數字資料
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period=period, interval=interval)
        
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

        # 嘗試取得股票名稱，若無則用代號代替
        stock_name = ticker.info.get('longName', stock_id)

        # 5. 計算即時價格與漲跌資訊
        latest_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
        change = latest_close - prev_close
        change_percent = (change / prev_close) * 100
        
        price_string = f"{latest_close:,.2f}"
        change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({'' if change >= 0 else ''}{change_percent:.2f}%)"
        color_theme = "#ff0000" if change >= 0 else "#008000" # 台灣紅漲綠跌

        # 6. 繪製 K 線圖
        buf = io.BytesIO()
        fig, axes = mpf.plot(
            df, type='candle', volume=True, returnfig=True, figsize=(8, 5),
            style='charles' # 使用標準查爾斯紅綠風格
        )
        
        # 加上對應時間頻率的標題
        axes[0].set_title(f"{stock_id} - {title_text}", fontsize=14)
        
        # 強制由 fig 執行儲存
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0) # 強制將記憶體指針撥回開頭
        plt.close(fig)

        # 7. 上傳圖片到 ImgBB
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        img_api_key = os.environ.get("IMGBB_API_KEY")
        
        if not img_api_key:
            print("ERROR: IMGBB_API_KEY is missing!")
            return jsonify({"status": "error", "message": "環境變數缺少 IMGBB_API_KEY"}), 200

        img_resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": img_api_key, "image": img_base64}
        )
        
        img_json = img_resp.json()
        
        # 🚨 【防空警報 2】檢查 ImgBB 是否上傳成功
        if img_resp.status_code != 200 or 'data' not in img_json:
            print(f"❌ 錯誤：ImgBB 上傳失敗！回應：{img_json}")
            # 圖表爆了改吐純文字版 Flex，避免 Make 卡死
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

        # 成功拿到乾淨的直接圖片網址
        final_image_url = img_json['data'].get('display_url', img_json['data'].get('url'))
        print(f"=== [DEBUG] 最新圖片網址 ===: {final_image_url}")

        # 8. 組裝完美的 K 線圖 LINE Flex Message 內容
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
                        "text": f"{title_text} 最新報價：{str(price_string)}",
                        "size": "md",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": f"漲跌幅：{str(change_string)}",
                        "size": "sm",
                        "color": color_theme,
                        "margin": "xs"
                    },
                    {"type": "separator", "margin": "lg"}
                ]
            }
        }

        # 動態將圖片塞入 Hero 區
        if final_image_url:
            image_block = {
                "type": "image",
                "url": str(final_image_url).strip(),
                "size": "full",
                "aspectMode": "cover",
                "aspectRatio": "20:13",
                "gravity": "center"
            }
            flex_contents["hero"] = image_block

        # 加入功能按鈕區塊
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
        # 確保 body 的 contents 存在才 append
        if "contents" in flex_contents["body"]:
            flex_contents["body"]["contents"].append(footer_block)

        # 9. 成功回傳大禮包給 Make.com
        return jsonify({
            "status": "success",
            "image_url": final_image_url,
            "flex_contents": flex_contents
        }), 200

    except Exception as e:
        print(f"💥 系統嚴重崩潰：{str(e)}")
        return jsonify({"status": "error", "message": f"Server Error: {str(e)}"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
