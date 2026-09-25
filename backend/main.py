import os
import re
import hashlib
import smtplib
import sqlite3
import asyncio
import calendar
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import numpy as np
import tifffile
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from web3 import Web3

load_dotenv()

REVERIFICATION_CHECK_INTERVAL = int(os.getenv("REVERIFICATION_CHECK_INTERVAL", "3600"))
SATELLITE_DIR = Path(os.getenv("SATELLITE_DATA_DIR", "satellite_data"))
SATELLITE_DIR.mkdir(parents=True, exist_ok=True)

TOKEN_URL = os.getenv("COPERNICUS_TOKEN_URL", "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token")
PROCESS_URL = os.getenv("COPERNICUS_PROCESS_URL", "https://sh.dataspace.copernicus.eu/process/v1")
CLIENT_ID = os.getenv("COPERNICUS_CLIENT_ID")
CLIENT_SECRET = os.getenv("COPERNICUS_CLIENT_SECRET")

TEAM_EMAIL = os.getenv("TEAM_EMAIL", "carbonvault26@gmail.com")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM", SMTP_USERNAME or "")

RPC_URL = os.getenv("BLOCKCHAIN_RPC_URL")
PRIVATE_KEY = os.getenv("BLOCKCHAIN_PRIVATE_KEY")
CONTRACT_ADDRESS = os.getenv("CARBONVAULT_CONTRACT_ADDRESS")

NDVI_ANOMALY_DROP = float(os.getenv("NDVI_ANOMALY_DROP", "0.10"))
GREEN_AREA_ANOMALY_DROP = float(os.getenv("GREEN_AREA_ANOMALY_DROP", "10.0"))
CARBON_PROXY_FACTOR = float(os.getenv("CARBON_PROXY_FACTOR", "0.5"))

DATABASE = os.getenv("CARBONVAULT_DATABASE", "carbonvault.db")

CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "string", "name": "_projectId", "type": "string"},
            {"internalType": "string", "name": "_dataHash", "type": "string"},
            {"internalType": "string", "name": "_status", "type": "string"}
        ],
        "name": "recordVerification",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def get_db():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def column_exists(conn, table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row["name"] == column_name for row in rows)

def add_column_if_missing(conn, column_name, column_definition):
    if not column_exists(conn, "projects", column_name):
        conn.execute(f"ALTER TABLE projects ADD COLUMN {column_name} {column_definition}")

def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT UNIQUE NOT NULL,
            company_name TEXT NOT NULL DEFAULT 'Unknown Company',
            location TEXT NOT NULL,
            area TEXT NOT NULL,
            bbox TEXT NOT NULL,
            date_from TEXT NOT NULL,
            date_to TEXT NOT NULL,
            user_email TEXT NOT NULL,
            retrieved_at TEXT,
            satellite_data_sha256 TEXT,
            uploaded_image_sha256 TEXT,
            baseline_satellite_path TEXT,
            mean_ndvi REAL,
            min_ndvi REAL,
            max_ndvi REAL,
            valid_pixels INTEGER,
            green_area_percent REAL,
            status TEXT NOT NULL,
            carbon_credits REAL DEFAULT 0,
            verifier_email TEXT,
            verifier_remarks TEXT,
            decision_at TEXT,
            blockchain_tx_hash TEXT,
            blockchain_status TEXT,
            blockchain_block_number INTEGER,
            previous_ndvi REAL,
            current_ndvi REAL,
            previous_green_area REAL,
            current_green_area REAL,
            reverification_status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    migrations = {
        "company_name": "TEXT NOT NULL DEFAULT 'Unknown Company'",
        "baseline_satellite_path": "TEXT",
        "reverification_due": "TEXT",
        "reverification_at": "TEXT",
        "reverification_status": "TEXT",
        "previous_ndvi": "REAL",
        "current_ndvi": "REAL",
        "ndvi_change": "REAL",
        "previous_green_area": "REAL",
        "current_green_area": "REAL",
        "green_area_change": "REAL",
        "previous_carbon_proxy": "REAL",
        "current_carbon_proxy": "REAL",
        "carbon_proxy_change": "REAL",
        "anomaly_flag": "INTEGER DEFAULT 0",
        "anomaly_reason": "TEXT",
        "reverification_data_sha256": "TEXT",
        "reverification_satellite_path": "TEXT",
        "reverification_tx_hash": "TEXT",
        "reverification_blockchain_status": "TEXT",
        "reverification_block_number": "INTEGER",
        "next_reverification_due": "TEXT",
        "blockchain_tx_hash": "TEXT",
        "blockchain_status": "TEXT",
        "blockchain_block_number": "INTEGER"
    }
    for name, definition in migrations.items():
        add_column_if_missing(conn, name, definition)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_project_id ON projects(project_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_reverification_due ON projects(reverification_due)")
    conn.commit()
    conn.close()

init_db()
reverification_task = None

@asynccontextmanager
async def lifespan(app):
    global reverification_task
    init_db()
    reverification_task = asyncio.create_task(reverification_scheduler())
    yield
    if reverification_task:
        reverification_task.cancel()
        try:
            await reverification_task
        except asyncio.CancelledError:
            pass

app = FastAPI(title="CarbonVault API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def sha256_bytes(data: bytes):
    return hashlib.sha256(data).hexdigest()

def validate_email(email: str):
    if not email:
        raise HTTPException(400, "Email address is required")
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(pattern, email):
        raise HTTPException(400, "Please enter a valid email address")

def parse_bbox(bbox: str):
    try:
        coords = [float(x.strip()) for x in bbox.split(",")]
        if len(coords)!= 4: raise ValueError
        min_lon, min_lat, max_lon, max_lat = coords
        if not (-180 <= min_lon < max_lon <= 180 and -90 <= min_lat < max_lat <= 90): raise ValueError
        return coords
    except Exception:
        raise HTTPException(400, "bbox must be minLon,minLat,maxLon,maxLat with valid WGS84 coordinates")

def parse_area_hectares(area_text: str):
    if not area_text: return 0.0
    text = area_text.lower().strip()
    match = re.search(r"([-+]?\d*\.?\d+)", text)
    if not match: return 0.0
    value = float(match.group(1))
    if "acre" in text: return value * 0.404686
    if "hectare" in text or re.search(r"\bha\b", text): return value
    if "sqm" in text or "m2" in text or "sq m" in text: return value / 10000.0
    if "km2" in text or "km²" in text or "sq km" in text: return value * 100.0
    return value

def add_six_months(date_value: datetime):
    month = date_value.month - 1 + 6
    year = date_value.year + month // 12
    month = (month % 12) + 1
    day = min(date_value.day, calendar.monthrange(year, month)[1])
    return date_value.replace(year=year, month=month, day=day)

def send_email(to_address: str, subject: str, body: str):
    if not SMTP_USERNAME or not SMTP_PASSWORD or not MAIL_FROM:
        return {"status": "NOT_CONFIGURED", "message": "SMTP credentials are not configured"}
    try:
        message = EmailMessage()
        message["From"] = MAIL_FROM
        message["To"] = to_address
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(message)
        return {"status": "SENT", "message": "Email sent successfully"}
    except Exception as exc:
        return {"status": "FAILED", "message": str(exc)[:300]}

async def get_token():
    if not CLIENT_ID or not CLIENT_SECRET:
        raise HTTPException(500, "Copernicus OAuth credentials are not configured in backend/.env")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if response.status_code!= 200:
        raise HTTPException(502, f"Copernicus authentication failed: {response.text[:400]}")
    data = response.json()
    if "access_token" not in data:
        raise HTTPException(502, "Copernicus did not return an access token")
    return data["access_token"]

NDVI_EVALSCRIPT = """//VERSION=3
function setup() { return { input: ["B04","B08","SCL","dataMask"], output: { bands: 2, sampleType: "FLOAT32" } }; }
function evaluatePixel(sample) {
  let cloudy = [3,8,9,10,11].includes(sample.SCL);
  let valid = sample.dataMask === 1 &&!cloudy;
  let denom = sample.B08 + sample.B04;
  let ndvi = denom === 0? -9999 : (sample.B08 - sample.B04) / denom;
  return [valid? ndvi : -9999, valid? 1 : 0];
}
"""

async def fetch_sentinel_ndvi(bbox, date_from, date_to):
    token = await get_token()
    payload = {
        "input": {"bounds": {"bbox": bbox, "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}}, "data": [{"type": "sentinel-2-l2a", "dataFilter": {"timeRange": {"from": f"{date_from}T00:00:00Z", "to": f"{date_to}T23:59:59Z"}, "mosaickingOrder": "leastCC"}}]},
        "output": {"width": 512, "height": 512, "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
        "evalscript": NDVI_EVALSCRIPT
    }
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(PROCESS_URL, json=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "image/tiff"})
    if response.status_code!= 200:
        raise RuntimeError(f"Sentinel-2 processing failed: {response.text[:500]}")
    if not response.content:
        raise RuntimeError("Sentinel-2 returned empty data")
    return response.content

def parse_ndvi_tiff(data: bytes):
    arr = tifffile.imread(BytesIO(data))
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 2:
        ndvi = arr
        mask = np.isfinite(ndvi)
    elif arr.ndim == 3:
        if arr.shape[0] == 2:
            ndvi = arr[0]; mask = arr[1]
        elif arr.shape[-1] == 2:
            ndvi = arr[..., 0]; mask = arr[..., 1]
        else:
            raise ValueError(f"Unexpected TIFF shape: {arr.shape}")
        mask = np.isfinite(ndvi) & (mask > 0.5)
    else:
        raise ValueError(f"Unexpected TIFF dimensions: {arr.ndim}")
    mask &= np.isfinite(ndvi) & (ndvi >= -1.0) & (ndvi <= 1.0)
    values = ndvi[mask]
    if values.size == 0:
        raise ValueError("No valid NDVI pixels returned")
    return {"mean": float(np.mean(values)), "min": float(np.min(values)), "max": float(np.max(values)), "valid_pixels": int(values.size), "green_area_percent": float(np.mean(values > 0.30) * 100.0)}

def calculate_carbon_impact_proxy(area_text, green_area_percent, mean_ndvi):
    area_hectares = parse_area_hectares(area_text)
    vegetation_area = area_hectares * green_area_percent / 100.0
    proxy = vegetation_area * max(mean_ndvi, 0) * CARBON_PROXY_FACTOR
    return float(proxy)

def record_on_blockchain(project_id: str, data_hash: str, status: str):
    if not RPC_URL or not PRIVATE_KEY or not CONTRACT_ADDRESS:
        return {"status": "NOT_CONFIGURED", "tx_hash": None, "message": "Blockchain environment is not configured"}
    try:
        w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
        if not w3.is_connected(): raise RuntimeError("Could not connect to Sepolia RPC")
        account = w3.eth.account.from_key(PRIVATE_KEY)
        contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        chain_id = w3.eth.chain_id
        tx = contract.functions.recordVerification(project_id, data_hash, status).build_transaction({"from": account.address, "nonce": nonce, "chainId": chain_id, "gas": 180000, "gasPrice": w3.eth.gas_price})
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        tx_hex = tx_hash.hex()
        if receipt.status!= 1:
            return {"status": "FAILED", "tx_hash": tx_hex, "block_number": receipt.blockNumber, "network": "Sepolia", "chain_id": chain_id, "message": "Transaction was mined but reverted"}
        return {"status": "CONFIRMED", "tx_hash": tx_hex, "block_number": receipt.blockNumber, "network": "Sepolia", "chain_id": chain_id, "recorder": account.address}
    except Exception as exc:
        return {"status": "FAILED", "tx_hash": None, "message": str(exc)[:400]}

def get_project(project_id: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM projects WHERE project_id =?", (project_id,)).fetchone()
    conn.close()
    return row

def check_duplicate_project(project_id: str):
    project = get_project(project_id)
    if project:
        raise HTTPException(status_code=409, detail=f"Project ID {project_id} is already registered with CarbonVault under company '{project['company_name']}'.")

def save_new_project(project_id, company_name, location, area, bbox, date_from, date_to, user_email, retrieved_at, satellite_hash, uploaded_hash, baseline_path, ndvi, status, carbon_proxy, blockchain):
    now = utc_now()
    retrieved_dt = datetime.fromisoformat(retrieved_at)
    next_due = add_six_months(retrieved_dt).isoformat()
    conn = get_db()
    conn.execute(
        """
        INSERT INTO projects (
            project_id, company_name, location, area, bbox, date_from, date_to, user_email,
            retrieved_at, satellite_data_sha256, uploaded_image_sha256, baseline_satellite_path,
            mean_ndvi, min_ndvi, max_ndvi, valid_pixels, green_area_percent,
            status, carbon_credits, blockchain_tx_hash, blockchain_status, blockchain_block_number,
            previous_carbon_proxy, current_carbon_proxy,
            reverification_status, reverification_due, next_reverification_due,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            project_id, company_name, location, area, bbox, date_from, date_to, user_email,
            retrieved_at, satellite_hash, uploaded_hash, str(baseline_path),
            ndvi["mean"], ndvi["min"], ndvi["max"], ndvi["valid_pixels"], ndvi["green_area_percent"],
            status, 0, blockchain.get("tx_hash"), blockchain.get("status"), blockchain.get("block_number"),
            carbon_proxy, carbon_proxy, "SCHEDULED", next_due, next_due, now, now
        )
    )
    conn.commit()
    conn.close()

@app.get("/api/health")
async def health():
    return {"ok": True, "service": "CarbonVault API", "version": "1.0.0", "blockchain_network": "Sepolia", "reverification": "Automatic 6-month monitoring"}

@app.post("/api/verify")
async def verify_project(project_id: str = Form(...), company_name: str = Form("Unknown Company"), location: str = Form(...), area: str = Form(...), bbox: str = Form(...), date_from: str = Form(...), date_to: str = Form(...), user_email: str = Form(...), satellite_image: UploadFile | None = File(None)):
    project_id = project_id.strip()
    company_name = company_name.strip() or "Unknown Company"
    location = location.strip()
    area = area.strip()
    user_email = user_email.strip()
    if not project_id: raise HTTPException(400, "Project ID is required")
    validate_email(user_email)
    coords = parse_bbox(bbox)
    check_duplicate_project(project_id)
    try:
        satellite_bytes = await fetch_sentinel_ndvi(coords, date_from, date_to)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Sentinel-2 processing failed: {str(exc)[:500]}")
    retrieved_hash = sha256_bytes(satellite_bytes)
    baseline_path = SATELLITE_DIR / f"{project_id}_baseline.tif"
    baseline_path.write_bytes(satellite_bytes)
    uploaded_hash = None
    if satellite_image:
        uploaded_bytes = await satellite_image.read()
        uploaded_hash = sha256_bytes(uploaded_bytes)
    try:
        ndvi = parse_ndvi_tiff(satellite_bytes)
    except Exception as exc:
        raise HTTPException(502, f"Sentinel-2 data was retrieved but NDVI could not be analysed: {str(exc)[:300]}")
    carbon_proxy = calculate_carbon_impact_proxy(area, ndvi["green_area_percent"], ndvi["mean"])
    retrieved_at = utc_now()
    blockchain = record_on_blockchain(project_id, retrieved_hash, "PENDING_TEAM_VERIFICATION")
    try:
        save_new_project(project_id, company_name, location, area, bbox, date_from, date_to, user_email, retrieved_at, retrieved_hash, uploaded_hash, baseline_path, ndvi, "PENDING_TEAM_VERIFICATION", carbon_proxy, blockchain)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"Project ID {project_id} is already registered.")
    user_mail = send_email(user_email, f"CarbonVault: Project {project_id} submitted", f"Project {project_id}\nMean NDVI: {ndvi['mean']:.4f}\nGreen: {ndvi['green_area_percent']:.2f}%\nCarbon Proxy: {carbon_proxy:.4f}\nSHA: {retrieved_hash}\nBlockchain: {blockchain.get('tx_hash')}\n")
    team_mail = send_email(TEAM_EMAIL, f"Inspection required for {project_id}", f"Company: {company_name}\nProject: {project_id}\nNDVI: {ndvi['mean']:.4f}\nGreen: {ndvi['green_area_percent']:.2f}%\nCarbon Proxy: {carbon_proxy:.4f}\nOwner: {user_email}\n")
    return {"project_id": project_id, "company_name": company_name, "location": location, "area": area, "status": "PENDING_TEAM_VERIFICATION", "message": "Sentinel-2 evidence retrieved successfully.", "team_email": TEAM_EMAIL, "user_email": user_email, "retrieved_at": retrieved_at, "reverification_due": add_six_months(datetime.fromisoformat(retrieved_at)).isoformat(), "satellite_data_sha256": retrieved_hash, "uploaded_image_sha256": uploaded_hash, "baseline_satellite_file": str(baseline_path), "ndvi": ndvi, "carbon_impact_proxy": carbon_proxy, "blockchain": blockchain, "email": {"user": user_mail, "team": team_mail}}

@app.post("/api/team-decision")
async def team_decision(project_id: str = Form(...), decision: str = Form(...), verifier_email: str = Form(...), remarks: str = Form(""), carbon_credits: float = Form(0)):
    decision = decision.strip().upper()
    validate_email(verifier_email)
    if decision not in ["APPROVED", "NOT_APPROVED"]: raise HTTPException(400, "decision must be APPROVED or NOT_APPROVED")
    project = get_project(project_id)
    if not project: raise HTTPException(404, f"Project {project_id} was not found")
    if decision == "NOT_APPROVED": carbon_credits = 0
    else:
        if carbon_credits <= 0: raise HTTPException(400, "Enter a positive prototype carbon-credit quantity")
    blockchain = record_on_blockchain(project_id, project["satellite_data_sha256"], decision)
    decision_time = utc_now()
    conn = get_db()
    conn.execute("UPDATE projects SET status =?, carbon_credits =?, verifier_email =?, verifier_remarks =?, decision_at =?, blockchain_tx_hash =?, blockchain_status =?, blockchain_block_number =?, updated_at =? WHERE project_id =?", (decision, carbon_credits, verifier_email, remarks, decision_time, blockchain.get("tx_hash"), blockchain.get("status"), blockchain.get("block_number"), decision_time, project_id))
    conn.commit()
    conn.close()
    user_mail = send_email(project["user_email"], f"Project {project_id} {decision}", f"Decision: {decision}\nCredits: {carbon_credits}\nTX: {blockchain.get('tx_hash')}\n")
    team_mail = send_email(TEAM_EMAIL, f"Decision recorded for {project_id}", f"Decision: {decision}\nVerifier: {verifier_email}\nTX: {blockchain.get('tx_hash')}\n")
    return {"project_id": project_id, "status": decision, "carbon_credits": carbon_credits, "verifier_email": verifier_email, "remarks": remarks, "decision_at": decision_time, "blockchain": blockchain, "email": {"user": user_mail, "team": team_mail}, "message": "Project approved." if decision == "APPROVED" else "Project was not approved."}

@app.get("/api/projects/{project_id}")
async def project_details(project_id: str):
    project = get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    return dict(project)

async def perform_reverification(project):
    project_id = project["project_id"]
    try:
        bbox = parse_bbox(project["bbox"])
        today = datetime.now(timezone.utc).date()
        new_date_to = today
        new_date_from = today - timedelta(days=30)
        new_satellite_bytes = await fetch_sentinel_ndvi(bbox, new_date_from.isoformat(), new_date_to.isoformat())
        new_path = SATELLITE_DIR / f"{project_id}_reverification_{today.isoformat()}.tif"
        new_path.write_bytes(new_satellite_bytes)
        new_hash = sha256_bytes(new_satellite_bytes)
        current_ndvi = parse_ndvi_tiff(new_satellite_bytes)
        previous_ndvi = {"mean": project["mean_ndvi"], "green_area_percent": project["green_area_percent"]}
        ndvi_change = current_ndvi["mean"] - previous_ndvi["mean"]
        green_area_change = current_ndvi["green_area_percent"] - previous_ndvi["green_area_percent"]
        previous_carbon = calculate_carbon_impact_proxy(project["area"], previous_ndvi["green_area_percent"], previous_ndvi["mean"])
        current_carbon = calculate_carbon_impact_proxy(project["area"], current_ndvi["green_area_percent"], current_ndvi["mean"])
        carbon_change = current_carbon - previous_carbon

        anomaly_reasons = []
        ndvi_drop = previous_ndvi["mean"] - current_ndvi["mean"]
        green_area_drop = previous_ndvi["green_area_percent"] - current_ndvi["green_area_percent"]
        if ndvi_drop >= NDVI_ANOMALY_DROP: anomaly_reasons.append(f"Significant NDVI decrease ({ndvi_drop:.4f})")
        if green_area_drop >= GREEN_AREA_ANOMALY_DROP: anomaly_reasons.append(f"Significant vegetation area decrease ({green_area_drop:.2f} percentage points)")
        anomaly = len(anomaly_reasons) > 0
        flag = "RED_FLAG" if anomaly else "GREEN_FLAG"
        reason = "; ".join(anomaly_reasons) if anomaly else "No significant vegetation decrease detected"

        blockchain = record_on_blockchain(project_id, new_hash, f"REVERIFICATION_{flag}")
        next_due = add_six_months(datetime.now(timezone.utc)).isoformat()
        now = utc_now()

        conn = get_db()
        conn.execute(
            """UPDATE projects SET previous_ndvi =?, current_ndvi =?, ndvi_change =?, previous_green_area =?, current_green_area =?, green_area_change =?, previous_carbon_proxy =?, current_carbon_proxy =?, carbon_proxy_change =?, anomaly_flag =?, anomaly_reason =?, reverification_status =?, reverification_at =?, reverification_data_sha256 =?, reverification_satellite_path =?, reverification_tx_hash =?, reverification_blockchain_status =?, reverification_block_number =?, reverification_due =?, next_reverification_due =?, updated_at =? WHERE project_id =?""",
            (previous_ndvi["mean"], current_ndvi["mean"], ndvi_change, previous_ndvi["green_area_percent"], current_ndvi["green_area_percent"], green_area_change, previous_carbon, current_carbon, carbon_change, 1 if anomaly else 0, reason, flag, now, new_hash, str(new_path), blockchain.get("tx_hash"), blockchain.get("status"), blockchain.get("block_number"), now, next_due, now, project_id)
        )
        conn.commit()
        conn.close()

        # LIVE CALC FOR FRONTEND - FIXED KEYS
        ndvi_change_percent = (ndvi_change / previous_ndvi["mean"] * 100) if previous_ndvi["mean"] else 0
        carbon_change_percent = (carbon_change / previous_carbon * 100) if previous_carbon else 0

        if anomaly:
            subject = f"CarbonVault ALERT: Reverification required for {project_id}"
            body = f"RED FLAG for {project_id}\nReason: {reason}\nPrev NDVI: {previous_ndvi['mean']:.4f}\nCurr: {current_ndvi['mean']:.4f}\nCarbon Prev: {previous_carbon:.4f}\nCarbon Curr: {current_carbon:.4f}\nTX: {blockchain.get('tx_hash')}\n"
            owner_mail = send_email(project["user_email"], subject, body)
            team_mail = send_email(TEAM_EMAIL, subject, body)
        else:
            owner_mail = {"status": "NOT_SENT", "message": "No anomaly"}
            team_mail = {"status": "NOT_SENT", "message": "No anomaly"}

        return {
            "project_id": project_id,
            "flag": flag,
            "anomaly": anomaly,
            "reason": reason,
            "message": reason,
            "previous_ndvi": previous_ndvi["mean"],
            "current_ndvi": current_ndvi["mean"],
            "ndvi_change": ndvi_change,
            "ndvi_change_percent": ndvi_change_percent,
            "previous_green_area": previous_ndvi["green_area_percent"],
            "current_green_area": current_ndvi["green_area_percent"],
            "green_area_change": green_area_change,
            "green_area_change_percent": green_area_change,
            "previous_carbon_proxy": previous_carbon,
            "current_carbon_proxy": current_carbon,
            "previous_carbon_estimate": previous_carbon,
            "current_carbon_estimate": current_carbon,
            "carbon_proxy_change": carbon_change,
            "carbon_change": carbon_change,
            "carbon_change_percent": carbon_change_percent,
            "blockchain": blockchain,
            "owner_email": owner_mail,
            "team_email": team_mail,
            "user_email": project["user_email"],
            "team_email_addr": TEAM_EMAIL,
            "reverification_date": now,
            "next_reverification": next_due
        }
    except Exception as exc:
        conn = get_db()
        conn.execute("UPDATE projects SET reverification_status = 'FAILED', anomaly_reason =?, updated_at =? WHERE project_id =?", (f"Automatic reverification failed: {str(exc)[:500]}", utc_now(), project_id))
        conn.commit()
        conn.close()
        return {"project_id": project_id, "flag": "REVERIFICATION_FAILED", "error": str(exc)[:500]}

async def reverification_scheduler():
    await asyncio.sleep(5)
    while True:
        try:
            now = datetime.now(timezone.utc)
            conn = get_db()
            rows = conn.execute("SELECT * FROM projects WHERE reverification_due IS NOT NULL AND reverification_due <=? AND (reverification_status IS NULL OR reverification_status NOT IN ('PROCESSING')) AND status = 'APPROVED'", (now.isoformat(),)).fetchall()
            for row in rows:
                conn.execute("UPDATE projects SET reverification_status = 'PROCESSING', updated_at =? WHERE project_id =?", (utc_now(), row["project_id"]))
            conn.commit()
            conn.close()
            for row in rows:
                project = get_project(row["project_id"])
                if project: await perform_reverification(project)
        except Exception as exc:
            print("Reverification scheduler error:", str(exc))
        await asyncio.sleep(REVERIFICATION_CHECK_INTERVAL)

@app.post("/api/reverification/{project_id}")
async def manual_reverification(project_id: str):
    project = get_project(project_id)
    if not project: raise HTTPException(404, "Project not found")
    if project["status"]!= "APPROVED": raise HTTPException(400, "Only APPROVED projects can enter automatic reverification.")
    conn = get_db()
    conn.execute("UPDATE projects SET reverification_status = 'PROCESSING', updated_at =? WHERE project_id =?", (utc_now(), project_id))
    conn.commit()
    conn.close()
    result = await perform_reverification(get_project(project_id))
    return result

@app.get("/api/dashboard")
async def dashboard():
    conn = get_db()
    rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    projects = [dict(row) for row in rows]
    return {
        "summary": {
            "total_projects": len(projects),
            "approved_projects": sum(1 for p in projects if p["status"] == "APPROVED"),
            "not_approved_projects": sum(1 for p in projects if p["status"] == "NOT_APPROVED"),
            "pending_projects": sum(1 for p in projects if p["status"] == "PENDING_TEAM_VERIFICATION"),
            "red_flag_projects": sum(1 for p in projects if p["reverification_status"] == "RED_FLAG"),
            "green_flag_projects": sum(1 for p in projects if p["reverification_status"] == "GREEN_FLAG"),
            "total_estimated_carbon_credits": sum(float(p["carbon_credits"] or 0) for p in projects)
        },
        "projects": projects
    }

@app.post("/api/reverification-notice")
async def reverification_notice(project_id: str = Form(...), location: str = Form(...), area: str = Form(...), user_email: str = Form(...), previous_ndvi: str = Form(""), current_ndvi: str = Form(""), flag: str = Form("REVERIFICATION_REQUIRED")):
    validate_email(user_email)
    subject = f"CarbonVault: Physical reverification required for {project_id}"
    user_body = f"Project {project_id} due for reverification.\nStatus: {flag}\nTeam: {TEAM_EMAIL}\n"
    team_body = f"Reverification required for {project_id}\nOwner: {user_email}\n"
    user_mail = send_email(user_email, subject, user_body)
    team_mail = send_email(TEAM_EMAIL, subject, team_body)
    return {"project_id": project_id, "status": "PHYSICAL_REVERIFICATION_REQUIRED", "user_email": user_email, "team_email": TEAM_EMAIL, "email": {"user": user_mail, "team": team_mail}, "message": "Physical reverification notice sent."}