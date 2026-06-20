import yfinance as yf
import mplfinance as mpf
import os
import requests
import base64
from flask import Flask, request, jsonify

app = Flask(__name__)

# ⚠️ 請把下方引號內換成你剛剛在 ImgBB 申請到的真實 API Key
IMGBB_API_KEY = "a01f9b3381ff4de813c23892ad038842"

@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        # --- 💥 超級防呆強壯版接收邏輯 💥 ---
        stock_id = "2330" # 預設值
        
        # 嘗試從各種可能的地方撈資料
        if request.is_json:
            req_data = request.get_json()
            # 確保 req_data 是一個字典，才使用 .get()
            if isinstance(req_data, dict):
                stock_id = req_data.get('stock_id', '2330')
        else:
            # 如果 Make.com 沒有用標準 JSON 傳，嘗試從表單或文字撈
            req_data = request.form or request.data
            if isinstance(req_data, dict):
                stock_id = req_data.get('stock_id', '2330')
            elif request.data:
                import json
                try:
                    raw_json = json.loads(request.data.decode('utf-8'))
                    stock_id = raw_json.get('stock_id', '2330')
                except:
                    # 如果真的解不開，直接把收到的東西當作代號（拿來防呆）
                    stock_id = request.data.decode('utf-8').strip()

        # 確保 stock_id 絕對是字串，且去掉雜質
        stock_id = str(stock_id).replace('"', '').replace("'", "").strip()
        # ------------------------------------

        # 自動修正台股尾巴
        if not stock_id.endswith('.TW') and not stock_id.endswith('.TWO'):
            full_stock_id = f"{stock_id}.TW"
        else:
            full_stock_id = stock_id

        print(f"📡 收到請求！正式抓取 {full_stock_id} 歷史數據...")
        # 抓取 3 個月歷史數據
        data = yf.download(full_stock_id, period="3mo")

        if data.empty:
            return jsonify({"status": "error", "message": "找不到這檔股票"}), 400

        data.columns = data.columns.get_level_values(0)
        
        # 定義圖片儲存路徑
        output_image = "my_stock_chart.png"
        
        # 繪製 K 線圖
        mpf.plot(data, type='candle', mav=(5, 20), volume=True, style='charles', 
                 title=f"\nStock {full_stock_id}", savefig=output_image)
        
        print("🎉 成功產生 K 線圖！開始上傳至雲端圖床...")

        # --- 自動上傳到 ImgBB ---
        with open(output_image, "rb") as file:
            img_base64 = base64.b64encode(file.read())
            
        img_bb_url = "https://api.imgbb.com/1/upload"
        payload = {
            "key": IMGBB_API_KEY,
            "image": img_base64,
            "expiration": 600 # 💥 設定這張圖片在雲端 10 分鐘後自動刪除，保護隱私不佔空間
        }
        
        response = requests.post(img_bb_url, data=payload)
        res_json = response.json()
        
        if response.status_code == 200 and res_json.get("success"):
            # 取得上傳成功後的真實圖片網址！
            uploaded_image_url = res_json["data"]["url"]
            print(f"🚀 圖片成功上傳雲端！網址為: {uploaded_image_url}")
            
            # 💥 把網址當作結果回傳給 Make.com
            return jsonify({
                "status": "success",
                "image_url": uploaded_image_url
            })
        else:
            return jsonify({"status": "error", "message": "圖床上傳失敗"}), 500
            
    except Exception as e:
        print(f"❌ 發生錯誤: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # 徹底簡化，直接指定 port=5000 並且開啟 debug 模式
    app.run(host='0.0.0.0', port=5000, debug=True)