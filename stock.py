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

        # 3. 透過 yfinance 抓取股票資料
        # 台灣股票代號需補上 .TW (例如 2313.TW)，防呆處理
        yf_stock_id = stock_id if stock_id.endswith(('.TW', '.TWO')) else f"{stock_id}.TW"
        ticker = yf.Ticker(yf_stock_id)
        df = ticker.history(period=period, interval=interval)

        if df.empty:
            # 如果加上 .TW 找不到，嘗試換成 .TWO (上櫃)
            yf_stock_id = f"{stock_id}.TWO"
            ticker = yf.Ticker(yf_stock_id)
            df = ticker.history(period=period, interval=interval)
            
        if df.empty:
            return jsonify({"status": "error", "message": f"找不到代碼 {stock_id} 的股票資料"}), 200

        # 4. 抓取即時市價與漲跌資訊
        info = ticker.info
        current_price = info.get('regularMarketPrice') or df['Close'].iloc[-1]
        prev_close = info.get('regularMarketPreviousClose') or df['Open'].iloc[0]
        
        # 處理即時價格歷史資料可能遺失的極端情況
        if current_price is None:
            current_price = 0.0
        if prev_close is None or prev_close == 0:
            prev_close = current_price if current_price != 0 else 1.0

        change = current_price - prev_close
        change_percent = (change / prev_close) * 100
        
        # 判斷漲跌顏色 (台灣股市：漲紅跌綠)
        color_theme = "#FF0000" if change >= 0 else "#00B000"
        change_sign = "+" if change >= 0 else ""
        price_string = f"{current_price:,.2f}"
        change_string = f"{change_sign}{change:,.2f} ({change_sign}{change_percent:.2f}%)"

        # 取得股票名稱
        stock_name = info.get('longName') or info.get('shortName') or stock_id

        # 5. 繪製 K 線圖 (終極除錯：改用最純粹、無中文的 matplotlib 測試)
        buf = io.BytesIO()
        
        # 建立一個最簡單的畫布，畫一條從 (0,0) 到 (1,1) 的藍色斜線
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot([0, 1], [0, 1], label='Test Line')
        ax.set_title(f"STOCK TEST - {stock_id}") # ❌ 完全不用中文
        ax.legend()
        
        # 儲存
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100)
        buf.seek(0)
        plt.close(fig)

        # --- 保持你原本的檢查代碼與 ImgBB 上傳不變 ---

        # --- 在這裡加入檢查代碼 ---
        img_api_key = os.environ.get("IMGBB_API_KEY")
        if not img_api_key:
            print("ERROR: IMGBB_API_KEY is missing!")
            return jsonify({"status": "error", "message": "ImgBB API Key 未設定"}), 200
        print(f"DEBUG: API KEY status: {len(img_api_key)} characters loaded.")
        # ------------------------
        
# 6. 上傳圖片到 ImgBB 取得圖片網址
        
        # 💡 [終極修正核心]：不管前面發生什麼事，在讀取前一刻強制把指針撥回 0！
        buf.seek(0) 
        
        # 緊接著立刻讀取並轉成 base64，不給任何程式介入的機會
        img_base64 = base64.b64encode(buf.read()).decode('utf-8')
        
        img_api_key = os.environ.get("IMGBB_API_KEY")
        if not img_api_key:
            return jsonify({"status": "error", "message": "環境變數缺少 IMGBB_API_KEY"}), 200

        img_resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": img_api_key, "image": img_base64}
        )
        
        if img_resp.status_code != 200 or 'data' not in img_resp.json():
            return jsonify({"status": "error", "message": "ImgBB 圖片上傳失敗"}), 200
            
        res_data = img_resp.json()['data']
        final_image_url = res_data.get('display_url', res_data.get('url'))
        
        print(f"=== [DEBUG] 最新圖片網址 ===: {final_image_url}")
        
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
