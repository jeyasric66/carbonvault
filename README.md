# CarbonVault — real Sentinel-2 + NDVI + email + blockchain integration

## What this version fixes
- Calculates mean/min/max NDVI from the real FLOAT32 GeoTIFF returned by Copernicus.
- Shows green/vegetated area percentage using NDVI > 0.30 as an analysis threshold.
- Sends a project-submission/inspection email to the project owner's email and a separate inspection email to the CarbonVault team.
- Writes the SHA-256 satellite evidence hash to an EVM-compatible blockchain when the blockchain environment is configured.
- Keeps final carbon-credit approval manual: the verification team must inspect the project and record the final decision.

Copernicus currently documents OAuth2 authentication and the Sentinel Hub Processing API at the official CDSE documentation. The Process API supports Sentinel-2 L2A and NDVI evalscripts. See the links below.

## 1. Backend
```bash
cd backend
python -m venv .venv
# Windows
.venv\\Scripts\\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env  # macOS/Linux
uvicorn main:app --reload
```

Fill `.env` with your Copernicus OAuth client ID and secret. Never put the client secret in frontend code.

## 2. Email
For Gmail SMTP, enable 2-Step Verification on the sending Gmail account and create a Gmail App Password. Put that App Password in `SMTP_PASSWORD`. Do not use your normal Gmail password.

The system sends:
1. User email: project received + physical inspection required.
2. Team email (`TEAM_EMAIL`): new project ready for site inspection.

If SMTP is not configured, the API reports `NOT_CONFIGURED` rather than pretending the message was sent.

## 3. Blockchain
The included Solidity contract is `contracts/CarbonVaultRegistry.sol`.

Deploy it to an EVM-compatible test network (for example Polygon Amoy) using Remix or Hardhat. Then set:
- `BLOCKCHAIN_RPC_URL`
- `BLOCKCHAIN_PRIVATE_KEY` — use a dedicated test wallet; never commit this value.
- `CARBONVAULT_CONTRACT_ADDRESS`

The backend submits `recordEvidence(projectId, sha256)` and waits for the transaction receipt. The UI then shows the transaction hash/status.

If blockchain configuration is missing, the UI reports `NOT_CONFIGURED`; it does not fabricate a transaction.

## 4. Frontend
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`.

Enter a real project email in the Project owner email field. This is the address that receives the physical-inspection notification.

## Important workflow
Sentinel-2 -> NDVI evidence -> SHA-256 -> blockchain evidence record -> email notification -> physical team inspection -> final APPROVED / NOT APPROVED decision.

Satellite analysis alone does not approve carbon credits.

## Official Copernicus docs
- https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Overview/Authentication.html
- https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process.html
- https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Process/Examples/S2L2A.html
