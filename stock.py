import os
import io
from flask import Flask, request, jsonify, send_file
import yfinance as yf
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  # 確保無顯示器環境不崩潰
import matplotlib.pyplot as plt

app = Flask(__name__)

# 🌟 建立一個全域字典，用來在記憶體中暫存圖片，避免寫入硬碟
IMAGE_CACHE = {}

# 1. 新增一個給 LINE 專用的抓圖路由
@app.route('/images/<stock_id>.png', methods=['GET'])
def serve_image(stock_id):
    # 從記憶體中把剛剛畫好的圖片字節拿出來
    img_bytes = IMAGE_CACHE.get(stock_id)
    if img_bytes:
        return send_file(io.BytesIO(img_bytes), mimetype='image/png')
    else:
        # 如果找不到，吐一張 1x1 的透明圖或 404
        return "Image not found", 404


@app.route('/get_chart', methods=['POST'])
def get_chart():
    try:
        # 1. 接收 Make.com 傳來的參數
        req_data = request.get_json() or {}
        stock_id = req_data.get('stock_id', '').strip()
        action_data = req_data.get('data', '').strip()

        if not stock_id:
            return jsonify({"status": "error", "message": "Missing stock_id"}), 200

        # 2. 判斷時間時段
        if action_data == '1m':
            period, interval, title_text = '1d', '1m', '1 Min K-Line'
        elif action_data == '5m':
            period, interval, title_text = '1d', '5m', '5 Min K-Line'
        elif action_data == 'weekly':
            period, interval, title_text = '1y', '1wk', 'Weekly K-Line'
        else:
            period, interval, title_text = '3mo', '1d', 'Daily K-Line'

        # 3. 抓取 yfinance 資料
        yf_code = f"{stock_id}.TW"
        ticker = yf.Ticker(yf_code)
        df = ticker.history(period=period, interval=interval)
        
        print(f"=== [DEBUG] 股票 {stock_id} 抓取到的資料筆數 ===: {df.shape}")
        
        if df.empty or len(df) < 2:
            return jsonify({
                "status": "error",
                "flex_contents": {
                    "type": "bubble",
                    "body": {
                        "type": "box", "layout": "vertical",
                        "contents": [{"type": "text", "text": "No enough data available.", "color": "#ff0000"}]
                    }
                }
            }), 200

        stock_name = ticker.info.get('longName', stock_id)

        # 4. 計算價格資訊
        latest_close = df['Close'].iloc[-1]
        prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
        change = latest_close - prev_close
        change_percent = (change / prev_close) * 100
        
        price_string = f"{latest_close:,.2f}"
        change_string = f"{'+' if change >= 0 else ''}{change:.2f} ({'' if change >= 0 else ''}{change_percent:.2f}%)"
        color_theme = "#ff0000" if change >= 0 else "#008000"

        # 5. 繪製 K 線圖
        buf = io.BytesIO()
        fig, axes = mpf.plot(
            df, type='candle', volume=True, returnfig=True, figsize=(10, 6),
            style='yahoo'
        )
        axes[0].set_title(f"STOCK: {stock_id} ({title_text})", fontsize=14, color='black')
        
        fig.savefig(buf, format='png', bbox_inches='tight', dpi=100, facecolor='white')
        
        # 🌟 將圖片字節存入全域快取字典中
        IMAGE_CACHE[stock_id] = buf.getvalue()
        
        file_size = len(IMAGE_CACHE[stock_id])
        print(f"=== [DEBUG] 自建快取圖片大小 ===: {file_size} bytes")
        
        buf.seek(0)
        plt.close('all')

        # 6. 動態獲取當前 Render 服務的根網址
        # 這樣就不管你的 app 叫什麼名字，它都會自動去抓
        base_url = request.url_root.rstrip('/')
        final_image_url = f"{base_url}/images/{stock_id}.png"
        print(f"=== [DEBUG] 本地自產圖片網址 ===: {final_image_url}")

        # 7. 組裝 LINE Flex Message
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
                        "text": f"{title_text} Price: {str(price_string)}",
                        "size": "md",
                        "margin": "md"
                    },
                    {
                        "type": "text",
                        "text": f"Change: {str(change_string)}",
                        "size": "sm",
                        "color": color_theme,
                        "margin": "xs"
                    },
                    {"type": "separator", "margin": "lg"}
                ]
            }
        }

        # 塞入直連圖片區
        image_block = {
            "type": "image",
            "url": str(final_image_url).strip(),
            "size": "full",
            "aspectMode": "cover",
            "aspectRatio": "20:13",
            "gravity": "center"
        }
        flex_contents["hero"] = image_block

        # 功能按鈕
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

        # 8. 回傳大禮包
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
