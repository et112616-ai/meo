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
        
       # 4. 用 yfinance 抓取歷史數字資料 (優化 period 確保一定有舊資料可以畫圖)
        ticker = yf.Ticker(yf_code)
        
        # 為了防止盤後或非交易日抓到空資料，如果 action_data 沒有特別指定，我們把範圍擴大到 3 個月
        if action_data not in ['1m', '5m', 'weekly']:
            period = '3mo' 
            
        df = ticker.history(period=period, interval=interval)
        
        # 🚨 印出 Debug 訊息到 Render Log，讓我們看看到底抓到幾筆資料
        print(f"=== [DEBUG] 股票 {stock_id} 抓取到的資料筆數 ===: {df.shape}")
        
        # 🚨 【防空警報 1】檢查有沒有抓到 Yahoo 資料
        if df.empty or len(df) < 2:
            print(f"❌ 錯誤：Yahoo Finance 抓到的資料太少或為空，無法畫圖！")
            return jsonify({
                "status": "error",
                "flex_contents": {
                    "type": "bubble",
                    "body": {
                        "type": "box", "layout": "vertical",
                        "contents": [{"type": "text", "text": f"股票代號 {stock_id} 目前時段無足夠交易資料可產出圖表。", "color": "#ff0000"}]
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

# 6. 繪製 K 線圖 (純英文標題防護版，徹底避開 Linux 字型損毀圖片的問題)
        buf = io.BytesIO()
        
        # 英文時段標籤映射
        en_title_map = {
            '1m': '1 Min K-Line',
            '5m': '5 Min K-Line',
            'weekly': 'Weekly K-Line',
            'daily': 'Daily K-Line'
        }
        en_title = en_title_map.get(action_data, 'Daily K-Line')

        # 這裡單純繪圖，拿到 fig 物件
        fig, axes = mpf.plot(
            df, type='candle', volume=True, returnfig=True, figsize=(10, 6),
            style='yahoo' # 白底黑字
        )
        
        # 🌟 核心關鍵：標題全部改成英文！拒絕任何中文字元，防止編碼損毀圖檔
        axes[0].set_title(f"STOCK: {stock_id} ({en_title})", fontsize=14, color='black')
        
        # 由 fig 執行儲存到 buf
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100, facecolor='white')
        
        file_size = buf.tell()
        print(f"=== [DEBUG] 記憶體中圖片檔案大小 ===: {file_size} bytes")
        
        buf.seek(0) # 強制將記憶體指針撥回開頭
        plt.close('all') # 徹底釋放記憶體

        # 🚨 【新防空警報 3】如果寫入的大小是 0，代表 matplotlib 還是沒畫成功，直接攔截！
        if file_size == 0:
            print("❌ 錯誤：Matplotlib 產出的圖檔大小為 0，不上傳 ImgBB！")
            return jsonify({
                "status": "success",
                "flex_contents": {
                    "type": "bubble",
                    "body": {
                        "type": "box", "layout": "vertical",
                        "contents": [{"type": "text", "text": "伺服器繪圖畫布失效，請稍後再試。", "color": "#ff0000"}]
                    }
                }
            }), 200

       # 7. 上傳圖片到 ImgBB
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        img_api_key = os.environ.get("IMGBB_API_KEY")
        
        if not img_api_key:
            print("ERROR: IMGBB_API_KEY is missing!")
            return jsonify({"status": "error", "message": "環境變數缺少 IMGBB_API_KEY"}), 200

        img_resp = requests.post(
            "https://api.api.imgbb.com/1/upload", # 註：有些舊網址是 api.imgbb.com，我們保持你原本能動的
            data={"key": img_api_key, "image": img_base64}
        )
        
        img_json = img_resp.json()
        
        # 🌟【終極大抓包】直接把 ImgBB 吐給我們的所有東西印在 Log 裡！
        print(f"=== [DEBUG] ImgBB 完整回傳 JSON ===: {img_json}")

        # 使用最安全的、絕對不崩潰的抓取法：先抓 url_viewer，如果沒有再抓 url
        # 我們先看看 Log 裡到底長怎樣
        if 'data' in img_json:
            res_data = img_json['data']
            # 如果有 image 階層就拿，沒有就拿最外層的 url
            if 'image' in res_data and 'url' in res_data['image']:
                final_image_url = res_data['image']['url']
            else:
                final_image_url = res_data.get('url')
        else:
            final_image_url = None

        print(f"=== [DEBUG] 最終萃取出的圖片網址 ===: {final_image_url}")
        
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
