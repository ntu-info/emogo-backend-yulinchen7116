from typing import Optional, List
import os
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import MongoClient

# ----（本機如果有 .env，可以用這段讀環境變數；在 Render 上只會用環境變數）----
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---- MongoDB 連線設定 ----
MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is not set. Please set it in .env or Render environment.")

client = MongoClient(MONGO_URI)
db = client["emogo"]            # database 名稱
entries_col = db["entries"]     # collection 名稱


# ---- Pydantic Model：定義一筆 EmoGo 資料 ----
class EmoEntry(BaseModel):
    id: Optional[int] = None
    latitude: float
    longitude: float
    mood: int
    photoUri: Optional[str] = None
    # 為了避免時間 parse 問題，用 str，前端送 ISO 字串即可
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


# ---- EmoGo API：新增紀錄（給前端丟資料）----
@app.post("/entries")
def create_entry(entry: EmoEntry):
    doc = entry.dict()
    result = entries_col.insert_one(doc)
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Insert failed")
    return {"status": "ok", "inserted_id": str(result.inserted_id)}


# ---- EmoGo API：列出所有紀錄（JSON，給之後前端用；你可以保留）----
@app.get("/entries")
def list_entries():
    docs: List[dict] = list(entries_col.find({}, {"_id": 0}))
    return {"data": docs}


# =========================
#       美化後 Export 頁面
# =========================

# ---- 總覽頁：列出四個漂亮頁面連結 ----
@app.get("/export", response_class=HTMLResponse)
def export_page():
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
        </style>
      </head>
      <body>
        <h1>EmoGo Data Export</h1>
        <p>Pretty HTML pages for viewing and downloading EmoGo data.</p>

        <div class="card">
          <h2>All data</h2>
          <ul>
            <li><a href="/export/all">All data (pretty view)</a></li>
          </ul>
        </div>

        <div class="card">
          <h2>Vlogs</h2>
          <ul>
            <li><a href="/export/vlogs">Vlogs (pretty view)</a></li>
          </ul>
        </div>

        <div class="card">
          <h2>Sentiments</h2>
          <ul>
            <li><a href="/export/sentiments">Sentiments (pretty view)</a></li>
          </ul>
        </div>

        <div class="card">
          <h2>GPS</h2>
          <ul>
            <li><a href="/export/gps">GPS coordinates (pretty view)</a></li>
          </ul>
        </div>
      </body>
    </html>
    """


# ---- All data：漂亮版 + 上面一鍵下載全部、每列下載單筆 JSON ----
@app.get("/export/all", response_class=HTMLResponse)
def export_all_html():
    docs = list(entries_col.find({}, {"_id": 0}))
    data_json = json.dumps(docs)

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo All Data</title>
        <style>
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f9fafb; }}
          h1 {{ margin-bottom: 0.2rem; }}
          p {{ margin-top: 0; color: #555; }}
          button {{ padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }}
          #download-all {{ background: #2563eb; color: white; margin-bottom: 12px; }}
          .download-single {{ background: #e5e7eb; color: #111827; }}
          .download-single:hover {{ background: #d1d5db; }}
          table {{ border-collapse: collapse; width: 100%; margin-top: 12px; background: white; }}
          th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }}
          th {{ background: #f3f4f6; }}
          tr:nth-child(even) td {{ background: #f9fafb; }}
          .container {{ max-width: 1100px; margin: 0 auto; }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>All EmoGo Data</h1>
          <p>Pretty view of all entries. Download all as one JSON file, or each entry separately.</p>
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
          const DATA = {data_json};

          function downloadJson(obj, filename) {{
            const blob = new Blob([JSON.stringify(obj, null, 2)], {{ type: "application/json" }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }}

          function renderTable() {{
            const tbody = document.querySelector("#data-table tbody");
            tbody.innerHTML = "";
            DATA.forEach((item, idx) => {{
              const tr = document.createElement("tr");
              tr.innerHTML =
                "<td>" + (idx + 1) + "</td>" +
                "<td>" + (item.id ?? "") + "</td>" +
                "<td>" + (item.latitude ?? "") + "</td>" +
                "<td>" + (item.longitude ?? "") + "</td>" +
                "<td>" + (item.mood ?? "") + "</td>" +
                "<td>" + (item.photoUri ?? "") + "</td>" +
                "<td>" + (item.timestamp ?? "") + "</td>" +
                "<td></td>";

              const btn = document.createElement("button");
              btn.textContent = "Download";
              btn.className = "download-single";
              btn.onclick = () => {{
                const filenameId = item.id !== undefined ? item.id : (idx + 1);
                downloadJson(item, "emogo_entry_" + filenameId + ".json");
              }};

              tr.lastElementChild.appendChild(btn);
              tbody.appendChild(tr);
            }});
          }}

          document.getElementById("download-all").onclick = () => {{
            downloadJson(DATA, "emogo_all_entries.json");
          }};

          renderTable();
        </script>
      </body>
    </html>
    """


# ---- Vlogs：只顯示 photoUri + timestamp ----
@app.get("/export/vlogs", response_class=HTMLResponse)
def export_vlogs_html():
    docs = list(
        entries_col.find(
            {},
            {"_id": 0, "id": 1, "photoUri": 1, "timestamp": 1},
        )
    )
    data_json = json.dumps(docs)

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo Vlogs</title>
        <style>
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f9fafb; }}
          h1 {{ margin-bottom: 0.2rem; }}
          p {{ margin-top: 0; color: #555; }}
          button {{ padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }}
          #download-all {{ background: #2563eb; color: white; margin-bottom: 12px; }}
          .download-single {{ background: #e5e7eb; color: #111827; }}
          .download-single:hover {{ background: #d1d5db; }}
          table {{ border-collapse: collapse; width: 100%; margin-top: 12px; background: white; }}
          th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }}
          th {{ background: #f3f4f6; }}
          tr:nth-child(even) td {{ background: #f9fafb; }}
          .container {{ max-width: 900px; margin: 0 auto; }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>EmoGo Vlogs</h1>
          <p>Pretty view of vlog entries (photoUri + timestamp).</p>
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
          const DATA = {data_json};

          function downloadJson(obj, filename) {{
            const blob = new Blob([JSON.stringify(obj, null, 2)], {{ type: "application/json" }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }}

          function renderTable() {{
            const tbody = document.querySelector("#data-table tbody");
            tbody.innerHTML = "";
            DATA.forEach((item, idx) => {{
              const tr = document.createElement("tr");
              tr.innerHTML =
                "<td>" + (idx + 1) + "</td>" +
                "<td>" + (item.id ?? "") + "</td>" +
                "<td>" + (item.photoUri ?? "") + "</td>" +
                "<td>" + (item.timestamp ?? "") + "</td>" +
                "<td></td>";

              const btn = document.createElement("button");
              btn.textContent = "Download";
              btn.className = "download-single";
              btn.onclick = () => {{
                const filenameId = item.id !== undefined ? item.id : (idx + 1);
                downloadJson(item, "emogo_vlog_" + filenameId + ".json");
              }};

              tr.lastElementChild.appendChild(btn);
              tbody.appendChild(tr);
            }});
          }}

          document.getElementById("download-all").onclick = () => {{
            downloadJson(DATA, "emogo_vlogs.json");
          }};

          renderTable();
        </script>
      </body>
    </html>
    """


# ---- Sentiments：只顯示 mood + timestamp ----
@app.get("/export/sentiments", response_class=HTMLResponse)
def export_sentiments_html():
    docs = list(
        entries_col.find(
            {},
            {"_id": 0, "id": 1, "mood": 1, "timestamp": 1},
        )
    )
    data_json = json.dumps(docs)

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo Sentiments</title>
        <style>
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f9fafb; }}
          h1 {{ margin-bottom: 0.2rem; }}
          p {{ margin-top: 0; color: #555; }}
          button {{ padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }}
          #download-all {{ background: #2563eb; color: white; margin-bottom: 12px; }}
          .download-single {{ background: #e5e7eb; color: #111827; }}
          .download-single:hover {{ background: #d1d5db; }}
          table {{ border-collapse: collapse; width: 100%; margin-top: 12px; background: white; }}
          th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }}
          th {{ background: #f3f4f6; }}
          tr:nth-child(even) td {{ background: #f9fafb; }}
          .container {{ max-width: 800px; margin: 0 auto; }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>EmoGo Sentiments</h1>
          <p>Pretty view of sentiment entries (mood + timestamp).</p>
          <button id="download-all">Download all sentiments as JSON</button>

          <table id="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>id</th>
                <th>mood</th>
                <th>timestamp</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <script>
          const DATA = {data_json};

          function downloadJson(obj, filename) {{
            const blob = new Blob([JSON.stringify(obj, null, 2)], {{ type: "application/json" }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }}

          function renderTable() {{
            const tbody = document.querySelector("#data-table tbody");
            tbody.innerHTML = "";
            DATA.forEach((item, idx) => {{
              const tr = document.createElement("tr");
              tr.innerHTML =
                "<td>" + (idx + 1) + "</td>" +
                "<td>" + (item.id ?? "") + "</td>" +
                "<td>" + (item.mood ?? "") + "</td>" +
                "<td>" + (item.timestamp ?? "") + "</td>" +
                "<td></td>";

              const btn = document.createElement("button");
              btn.textContent = "Download";
              btn.className = "download-single";
              btn.onclick = () => {{
                const filenameId = item.id !== undefined ? item.id : (idx + 1);
                downloadJson(item, "emogo_sentiment_" + filenameId + ".json");
              }};

              tr.lastElementChild.appendChild(btn);
              tbody.appendChild(tr);
            }});
          }}

          document.getElementById("download-all").onclick = () => {{
            downloadJson(DATA, "emogo_sentiments.json");
          }};

          renderTable();
        </script>
      </body>
    </html>
    """


# ---- GPS：只顯示 latitude / longitude + timestamp ----
@app.get("/export/gps", response_class=HTMLResponse)
def export_gps_html():
    docs = list(
        entries_col.find(
            {},
            {"_id": 0, "id": 1, "latitude": 1, "longitude": 1, "timestamp": 1},
        )
    )
    data_json = json.dumps(docs)

    return f"""
    <html>
      <head>
        <meta charset="utf-8" />
        <title>EmoGo GPS</title>
        <style>
          body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 24px; background: #f9fafb; }}
          h1 {{ margin-bottom: 0.2rem; }}
          p {{ margin-top: 0; color: #555; }}
          button {{ padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }}
          #download-all {{ background: #2563eb; color: white; margin-bottom: 12px; }}
          .download-single {{ background: #e5e7eb; color: #111827; }}
          .download-single:hover {{ background: #d1d5db; }}
          table {{ border-collapse: collapse; width: 100%; margin-top: 12px; background: white; }}
          th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }}
          th {{ background: #f3f4f6; }}
          tr:nth-child(even) td {{ background: #f9fafb; }}
          .container {{ max-width: 900px; margin: 0 auto; }}
        </style>
      </head>
      <body>
        <div class="container">
          <h1>EmoGo GPS</h1>
          <p>Pretty view of GPS entries (latitude / longitude + timestamp).</p>
          <button id="download-all">Download all GPS as JSON</button>

          <table id="data-table">
            <thead>
              <tr>
                <th>#</th>
                <th>id</th>
                <th>latitude</th>
                <th>longitude</th>
                <th>timestamp</th>
                <th>Download</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>

        <script>
          const DATA = {data_json};

          function downloadJson(obj, filename) {{
            const blob = new Blob([JSON.stringify(obj, null, 2)], {{ type: "application/json" }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }}

          function renderTable() {{
            const tbody = document.querySelector("#data-table tbody");
            tbody.innerHTML = "";
            DATA.forEach((item, idx) => {{
              const tr = document.createElement("tr");
              tr.innerHTML =
                "<td>" + (idx + 1) + "</td>" +
                "<td>" + (item.id ?? "") + "</td>" +
                "<td>" + (item.latitude ?? "") + "</td>" +
                "<td>" + (item.longitude ?? "") + "</td>" +
                "<td>" + (item.timestamp ?? "") + "</td>" +
                "<td></td>";

              const btn = document.createElement("button");
              btn.textContent = "Download";
              btn.className = "download-single";
              btn.onclick = () => {{
                const filenameId = item.id !== undefined ? item.id : (idx + 1);
                downloadJson(item, "emogo_gps_" + filenameId + ".json");
              }};

              tr.lastElementChild.appendChild(btn);
              tbody.appendChild(tr);
            }});
          }}

          document.getElementById("download-all").onclick = () => {{
            downloadJson(DATA, "emogo_gps.json");
          }};

          renderTable();
        </script>
      </body>
    </html>
    """
