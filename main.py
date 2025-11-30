from typing import Optional, List
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import MongoClient

# ----（本機開發時，如果有用 .env 就打開這段）----
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # 如果沒有裝 python-dotenv 就略過，Render 上只會用環境變數
    pass

# ---- MongoDB 連線設定 ----
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    # 這樣在本機沒設定 MONGO_URI 的時候會看得出問題
    raise RuntimeError("MONGO_URI is not set. Please set it in .env or Render environment.")

client = MongoClient(MONGO_URI)
db = client["emogo"]           # database 名稱，可改
entries_col = db["entries"]    # collection 名稱，可改


# ---- Pydantic Model：定義一筆 EmoGo 資料長相 ----
class EmoEntry(BaseModel):
    id: Optional[int] = None
    latitude: float
    longitude: float
    mood: int
    photoUri: Optional[str] = None
    # 為了避免時間格式 parse 問題，這裡用 str，前端就送 ISO 字串
    timestamp: str


# ---- 建立 FastAPI app ----
app = FastAPI()

# ---- CORS 設定（讓 Expo / Web 前端可以叫這個 API）----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 作業方便，先全開
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 基本測試用 endpoints ----
@app.get("/")
def root():
    return {"message": "EmoGo backend is running."}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: Optional[str] = None):
    return {"item_id": item_id, "q": q}


# ---- EmoGo 主要 API：新增紀錄 ----
@app.post("/entries")
def create_entry(entry: EmoEntry):
    doc = entry.dict()
    result = entries_col.insert_one(doc)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"status": "ok", "inserted_id": str(result.inserted_id)}


# ---- EmoGo 主要 API：列出所有紀錄（純 JSON）----
@app.get("/entries")
def list_entries():
    # 投影片／TA 看資料時，不一定想看到 MongoDB 的 _id，就先隱藏
    docs: List[dict] = list(entries_col.find({}, {"_id": 0}))
    return {"data": docs}


# ---- 匯出三種資料：Vlogs / Sentiments / GPS / All ----
@app.get("/export/vlogs")
def export_vlogs():
    docs = list(
        entries_col.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "photoUri": 1,
                "timestamp": 1,
            },
        )
    )
    return {"vlogs": docs}

@app.get("/export/vlogs/html", response_class=HTMLResponse)
def export_vlogs_html():
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo Vlogs</title>
        <style>
          body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f9fafb; }
          h1 { margin-bottom: 0.2rem; }
          p { margin-top: 0; color: #555; }
          button { padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
          #download-all { background: #2563eb; color: white; margin-bottom: 12px; }
          .download-single { background: #e5e7eb; color: #111827; }
          .download-single:hover { background: #d1d5db; }
          table { border-collapse: collapse; width: 100%; margin-top: 12px; background: white; }
          th, td { border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }
          th { background: #f3f4f6; }
          tr:nth-child(even) td { background: #f9fafb; }
          .container { max-width: 900px; margin: 0 auto; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>EmoGo Vlogs</h1>
          <p>Pretty view of <code>/export/vlogs</code>. Each row is a vlog entry.</p>
          <button id="download-all">Download all vlogs as JSON</button>

          <table id="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>id</th>
                <th>photoUri</th>
                <th>timestamp</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <script>
          function downloadJson(obj, filename) {
            const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }

          async function loadData() {
            const res = await fetch("/export/vlogs");
            const json = await res.json();
            const data = json.vlogs || [];
            const tbody = document.querySelector("#data-table tbody");

            data.forEach((item, idx) => {
              const tr = document.createElement("tr");
              tr.innerHTML = `
                <td>${idx + 1}</td>
                <td>${item.id ?? ""}</td>
                <td>${item.photoUri ?? ""}</td>
                <td>${item.timestamp ?? ""}</td>
                <td></td>
              `;

              const btn = document.createElement("button");
              btn.textContent = "Download";
              btn.className = "download-single";
              btn.onclick = () => {
                const filenameId = item.id !== undefined ? item.id : (idx + 1);
                downloadJson(item, `emogo_vlog_${filenameId}.json`);
              };

              tr.lastElementChild.appendChild(btn);
              tbody.appendChild(tr);
            });

            document.getElementById("download-all").onclick = () => {
              downloadJson(data, "emogo_vlogs.json");
            };
          }

          loadData();
        </script>
      </body>
    </html>
    """


@app.get("/export/sentiments")
def export_sentiments():
    docs = list(
        entries_col.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "mood": 1,
                "timestamp": 1,
            },
        )
    )
    return {"sentiments": docs}


@app.get("/export/gps")
def export_gps():
    docs = list(
        entries_col.find(
            {},
            {
                "_id": 0,
                "id": 1,
                "latitude": 1,
                "longitude": 1,
                "timestamp": 1,
            },
        )
    )
    return {"gps": docs}


@app.get("/export/all")
def export_all():
    docs = list(entries_col.find({}, {"_id": 0}))
    return {"data": docs}

@app.get("/export/all/html", response_class=HTMLResponse)
def export_all_html():
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo All Data</title>
        <style>
          body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f9fafb; }
          h1 { margin-bottom: 0.2rem; }
          p { margin-top: 0; color: #555; }
          button { padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
          #download-all { background: #2563eb; color: white; margin-bottom: 12px; }
          .download-single { background: #e5e7eb; color: #111827; }
          .download-single:hover { background: #d1d5db; }
          table { border-collapse: collapse; width: 100%; margin-top: 12px; background: white; }
          th, td { border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }
          th { background: #f3f4f6; }
          tr:nth-child(even) td { background: #f9fafb; }
          .container { max-width: 1000px; margin: 0 auto; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>All EmoGo Data</h1>
          <p>Pretty view of <code>/export/all</code>. You can download all entries or each one individually.</p>
          <button id="download-all">Download all as JSON</button>

          <table id="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>id</th>
                <th>latitude</th>
                <th>longitude</th>
                <th>mood</th>
                <th>photoUri</th>
                <th>timestamp</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <script>
          function downloadJson(obj, filename) {
            const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }

          async function loadData() {
            const res = await fetch("/export/all");
            const json = await res.json();
            const data = json.data || [];
            const tbody = document.querySelector("#data-table tbody");

            data.forEach((item, idx) => {
              const tr = document.createElement("tr");
              tr.innerHTML = `
                <td>${idx + 1}</td>
                <td>${item.id ?? ""}</td>
                <td>${item.latitude ?? ""}</td>
                <td>${item.longitude ?? ""}</td>
                <td>${item.mood ?? ""}</td>
                <td>${item.photoUri ?? ""}</td>
                <td>${item.timestamp ?? ""}</td>
                <td></td>
              `;

              const btn = document.createElement("button");
              btn.textContent = "Download";
              btn.className = "download-single";
              btn.onclick = () => {
                const filenameId = item.id !== undefined ? item.id : (idx + 1);
                downloadJson(item, `emogo_entry_${filenameId}.json`);
              };

              tr.lastElementChild.appendChild(btn);
              tbody.appendChild(tr);
            });

            document.getElementById("download-all").onclick = () => {
              downloadJson(data, "emogo_all_entries.json");
            };
          }

          loadData();
        </script>
      </body>
    </html>
    """


# ---- 匯出頁面（作業要求的 data-exporting/downloading page）----
@app.get("/export", response_class=HTMLResponse)
def export_page():
    # 這個頁面只是導航：JSON + 美化版兩種都列出
    return """
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo Data Export</title>
        <style>
          body { font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f5f5f5; }
          h1 { margin-bottom: 0.2rem; }
          p { margin-top: 0; color: #555; }
          .card { background: #fff; border-radius: 8px; padding: 16px 20px; margin-top: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); }
          ul { margin: 0; padding-left: 20px; }
          a { color: #2563eb; text-decoration: none; }
          a:hover { text-decoration: underline; }
          .json-tag { font-size: 12px; color: #555; background: #e5e7eb; padding: 2px 6px; border-radius: 4px; margin-left: 4px; }
        </style>
      </head>
      <body>
        <h1>EmoGo Data Export</h1>
        <p>You can view or download EmoGo data below.</p>

        <div class="card">
          <h2>All data</h2>
          <ul>
            <li>JSON API: <a href="/export/all" target="_blank">/export/all</a><span class="json-tag">raw JSON</span></li>
            <li>Pretty view: <a href="/export/all/html" target="_blank">/export/all/html</a></li>
          </ul>
        </div>

        <div class="card">
          <h2>Vlogs</h2>
          <ul>
            <li>JSON API: <a href="/export/vlogs" target="_blank">/export/vlogs</a><span class="json-tag">raw JSON</span></li>
            <li>Pretty view: <a href="/export/vlogs/html" target="_blank">/export/vlogs/html</a></li>
          </ul>
        </div>

        <div class="card">
          <h2>Sentiments</h2>
          <ul>
            <li>JSON API: <a href="/export/sentiments" target="_blank">/export/sentiments</a><span class="json-tag">raw JSON</span></li>
            <li>Pretty view: <a href="/export/sentiments/html" target="_blank">/export/sentiments/html</a></li>
          </ul>
        </div>

        <div class="card">
          <h2>GPS</h2>
          <ul>
            <li>JSON API: <a href="/export/gps" target="_blank">/export/gps</a><span class="json-tag">raw JSON</span></li>
            <li>Pretty view: <a href="/export/gps/html" target="_blank">/export/gps/html</a></li>
          </ul>
        </div>
      </body>
    </html>
    """
