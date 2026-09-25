import React, { useEffect, useState } from "react";

const API = "http://localhost:8000";

export default function App() {
  const [mode, setMode] = useState("login");
  const [page, setPage] = useState("home");

  const [form, setForm] = useState({
    userId: "",
    email: "",
    password: "",
    company: "",
  });

  const [project, setProject] = useState({
    project_id: "",
    company_name: "",
    location: "",
    area: "",
    bbox: "",
    date_from: "",
    date_to: "",
    user_email: "",
    image: null,
  });

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [dashboard, setDashboard] = useState(null);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [teamProjectId, setTeamProjectId] = useState("");
  const [teamProject, setTeamProject] = useState(null);
  const [teamDecision, setTeamDecision] = useState({
    decision: "",
    verifier_email: "",
    remarks: "",
    carbon_credits: "",
  });
  const [teamLoading, setTeamLoading] = useState(false);
  const [teamMessage, setTeamMessage] = useState("");
  const [reverifyProjectId, setReverifyProjectId] = useState("");
  const [reverifyResult, setReverifyResult] = useState(null);
  const [reverifyLoading, setReverifyLoading] = useState(false);

  function change(e) {
    setForm({...form, [e.target.name]: e.target.value });
  }
  function updateProject(key, value) {
    setProject((p) => ({...p, [key]: value }));
  }

  async function loadDashboard() {
    setDashboardLoading(true);
    setError("");
    try {
      const response = await fetch(`${API}/api/dashboard`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load dashboard");
      setDashboard(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setDashboardLoading(false);
    }
  }

  useEffect(() => {
    if (page === "dashboard") loadDashboard();
  }, [page]);

  async function loadTeamProject() {
    setError("");
    setTeamMessage("");
    setTeamProject(null);
    if (!teamProjectId.trim()) {
      setError("Enter a Project ID");
      return;
    }
    setTeamLoading(true);
    try {
      const response = await fetch(`${API}/api/projects/${encodeURIComponent(teamProjectId.trim())}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Project not found");
      setTeamProject(data);
      setTeamDecision({ decision: "", verifier_email: "carbonvault26@gmail.com", remarks: "", carbon_credits: "" });
    } catch (e) {
      setError(e.message);
    } finally {
      setTeamLoading(false);
    }
  }

  async function submitTeamDecision() {
    setError("");
    setTeamMessage("");
    if (!teamProject) { setError("Load a project first"); return; }
    if (!teamDecision.decision) { setError("Select APPROVED or NOT APPROVED"); return; }
    if (!teamDecision.verifier_email) { setError("Enter verification team email"); return; }
    if (teamDecision.decision === "APPROVED" && Number(teamDecision.carbon_credits) <= 0) {
      setError("Enter the prototype estimated carbon-credit quantity");
      return;
    }
    setTeamLoading(true);
    try {
      const fd = new FormData();
      fd.append("project_id", teamProject.project_id);
      fd.append("decision", teamDecision.decision);
      fd.append("verifier_email", teamDecision.verifier_email);
      fd.append("remarks", teamDecision.remarks);
      fd.append("carbon_credits", teamDecision.decision === "APPROVED"? teamDecision.carbon_credits : "0");
      const response = await fetch(`${API}/api/team-decision`, { method: "POST", body: fd });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not record decision");
      setTeamMessage("Final team decision recorded successfully.");
      await loadTeamProject();
      await loadDashboard();
    } catch (e) {
      setError(e.message);
    } finally {
      setTeamLoading(false);
    }
  }

  async function fetchSatellite() {
    setError("");
    setResult(null);
    setLoading(true);
    try {
      if (!project.project_id.trim()) throw new Error("Project ID is required");
      if (!project.company_name.trim()) throw new Error("Company name is required");
      if (!project.user_email.trim()) throw new Error("Project owner email is required");
      const fd = new FormData();
      fd.append("project_id", project.project_id);
      fd.append("company_name", project.company_name);
      fd.append("location", project.location);
      fd.append("area", project.area);
      fd.append("bbox", project.bbox);
      fd.append("date_from", project.date_from);
      fd.append("date_to", project.date_to);
      fd.append("user_email", project.user_email || form.email);
      if (project.image) fd.append("satellite_image", project.image);
      const response = await fetch(`${API}/api/verify`, { method: "POST", body: fd });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Verification request failed");
      setResult(data);
      setTeamProjectId(data.project_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function runReverification() {
    setError("");
    setReverifyResult(null);
    if (!reverifyProjectId.trim()) { setError("Enter a Project ID"); return; }
    setReverifyLoading(true);
    try {
      const response = await fetch(`${API}/api/reverification/${encodeURIComponent(reverifyProjectId.trim())}`, { method: "POST" });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Reverification failed");
      setReverifyResult(data);
      await loadDashboard();
    } catch (e) {
      setError(e.message);
    } finally {
      setReverifyLoading(false);
    }
  }

  if (page === "home") {
    return (
      <main className="landing">
        <div className="glow"></div>
        <nav><div className="brand"><span>◈</span> CARBON<span>VAULT</span></div><div className="pill">BLOCKCHAIN × EARTH OBSERVATION</div></nav>
        <section className="hero">
          <div>
            <p className="eyebrow">CARBON CREDIT VERIFICATION PLATFORM</p>
            <h1>Verify carbon.<br /><em>Trust the data.</em></h1>
            <p className="sub">Sentinel-2 satellite evidence, NDVI monitoring, cryptographic integrity and human-led verification in one platform.</p>
            <button onClick={() => setPage("auth")}>Get Started <b>→</b></button>
          </div>
          <div className="orb"><div className="ring r1"></div><div className="ring r2"></div><div className="leaf">♧</div><small>SENTINEL-2<br />VERIFICATION</small></div>
        </section>
        <div className="features"><span>🛰️ Sentinel-2</span><span>🌿 NDVI</span><span>🔐 SHA-256</span><span>⛓️ Blockchain</span><span>👷 Team Approval</span><span>🔄 6-Month Monitoring</span></div>
      </main>
    );
  }

  if (page === "auth") {
    return (
      <main className="authPage">
        <div className="authCard">
          <div className="brand big"><span>◈</span> CARBON<span>VAULT</span></div>
          <p className="muted">Blockchain-Based Carbon Credit Verification</p>
          <div className="tabs">
            <button className={mode === "login"? "active" : ""} onClick={() => setMode("login")}>Login</button>
            <button className={mode === "register"? "active" : ""} onClick={() => setMode("register")}>Register</button>
          </div>
          <label>User ID<input name="userId" value={form.userId} onChange={change} placeholder="Enter user ID" /></label>
          {mode === "register" && <label>Company Name<input name="company" value={form.company} onChange={change} placeholder="Company / Organization" /></label>}
          <label>Email<input name="email" type="email" value={form.email} onChange={change} placeholder="you@example.com" /></label>
          <label>Password<input name="password" type="password" value={form.password} onChange={change} placeholder="••••••••" /></label>
          {mode === "register" && <label>Confirm Password<input type="password" placeholder="••••••••" /></label>}
          <button className="full" onClick={() => {
            if (!form.email) { setError("Please enter your email"); return; }
            if (mode === "register" &&!form.company) { setError("Please enter company name"); return; }
            setProject((p) => ({...p, user_email: form.email, company_name: form.company }));
            setError(""); setPage("dashboard");
          }}>{mode === "login"? "Login" : "Create Account"} →</button>
          {error && <div className="error">{error}</div>}
          <p className="muted tiny">Each company must use a unique Project ID. A Project ID already registered by another company cannot be reused.</p>
        </div>
      </main>
    );
  }

  if (page === "team") {
    return (
      <main className="app">
        <aside>
          <div className="brand"><span>◈</span> CARBON<span>VAULT</span></div>
          <button className="nav" onClick={() => setPage("dashboard")}>⌂ Dashboard</button>
          <button className="nav" onClick={() => setPage("verify")}>＋ New Verification</button>
          <button className="nav active">✓ Team Verification</button>
          <button className="nav" onClick={() => setPage("reverify")}>↻ Reverification</button>
          <div className="sideBottom">VERIFICATION TEAM<br /><b>carbonvault26@gmail.com</b></div>
        </aside>
        <section className="content">
          <header><div><p className="eyebrow">CARBON VAULT / TEAM</p><h2>Physical Verification</h2></div><div className="avatar">T</div></header>
          <div className="notice"><span>●</span><div><b>Final approval is performed by the verification team</b><p>Satellite data does not automatically approve carbon credits. The team must physically inspect the project.</p></div></div>
          <div className="card">
            <h3>Find Project</h3><p className="muted">Enter the Project ID received by the verification team.</p>
            <label>Project ID<input value={teamProjectId} onChange={(e) => setTeamProjectId(e.target.value)} placeholder="CV-PROJ-001" /></label>
            <button className="fetch" onClick={loadTeamProject} disabled={teamLoading}>{teamLoading? "Loading..." : "Load Project →"}</button>
          </div>

          {teamProject && (
            <div className="result">
              <div className="status">● {teamProject.status}</div>
              <h3>Project Inspection</h3>
              <div className="metrics">
                <div><small>Project</small><strong>{teamProject.project_id}</strong></div>
                <div><small>Company</small><strong>{teamProject.company_name}</strong></div>
                <div><small>Location</small><strong>{teamProject.location}</strong></div>
              </div>

              <div className="metrics">
                <div><small>Baseline NDVI</small><strong>{Number(teamProject.mean_ndvi || 0).toFixed(4)}</strong></div>
                <div><small>Green Area</small><strong>{Number(teamProject.green_area_percent || 0).toFixed(2)}%</strong></div>
                {/* FIXED BLOCKCHAIN DISPLAY */}
                <div>
                  <small>Blockchain</small>
                  {teamProject.blockchain_tx_hash? (
                    <div>
                      <strong style={{color:"#22c55e"}}>RECORDED</strong>
                      <div style={{fontSize:"10px", wordBreak:"break-all", marginTop:"4px", color:"#9ca3af"}}>
                        {teamProject.blockchain_tx_hash}
                      </div>
                      <a href={`https://sepolia.etherscan.io/tx/${teamProject.blockchain_tx_hash.startsWith("0x")? teamProject.blockchain_tx_hash : "0x"+teamProject.blockchain_tx_hash}`} target="_blank" rel="noreferrer" style={{fontSize:"11px", color:"#60a5fa", textDecoration:"underline"}}>
                        View on Etherscan →
                      </a>
                      <div style={{fontSize:"10px", color:"#6b7280"}}>Block: {teamProject.blockchain_block_number || "—"}</div>
                    </div>
                  ) : (
                    <strong>{teamProject.blockchain_status === "CONFIRMED"? "RECORDED" : teamProject.blockchain_status || "PENDING"}</strong>
                  )}
                </div>
              </div>

              {teamProject.status === "PENDING_TEAM_VERIFICATION" && (
                <div className="teamDecision">
                  <h3>Physical Inspection Decision</h3>
                  <label>Verification Team Email<input type="email" value={teamDecision.verifier_email} onChange={(e) => setTeamDecision((d) => ({...d, verifier_email: e.target.value }))} /></label>
                  <label>Inspection Remarks<textarea value={teamDecision.remarks} onChange={(e) => setTeamDecision((d) => ({...d, remarks: e.target.value }))} rows="5" placeholder="Physical inspection observations..." /></label>
                  <label>Estimated Carbon Credits<span className="hint">prototype quantity</span><input type="number" min="0" step="0.01" value={teamDecision.carbon_credits} onChange={(e) => setTeamDecision((d) => ({...d, carbon_credits: e.target.value }))} /></label>
                  <div className="decisionButtons">
                    <button className="approve" onClick={() => setTeamDecision((d) => ({...d, decision: "APPROVED" }))}>✓ APPROVE PROJECT</button>
                    <button className="reject" onClick={() => setTeamDecision((d) => ({...d, decision: "NOT_APPROVED" }))}>✕ NOT APPROVE</button>
                  </div>
                  {teamDecision.decision && <div className="selectedDecision">Selected:<b> {teamDecision.decision}</b></div>}
                  <button className="fetch" onClick={submitTeamDecision} disabled={teamLoading ||!teamDecision.decision}>{teamLoading? "Recording..." : "Record Final Team Decision →"}</button>
                </div>
              )}

              {teamProject.status === "APPROVED" && (
                <div className="approvalBox">
                  <h3>✓ PROJECT APPROVED</h3>
                  <p>Final approval was recorded by the verification team.</p>
                  <div className="metrics">
                    <div><small>Estimated Credits</small><strong>{Number(teamProject.carbon_credits || 0).toFixed(2)}</strong></div>
                    <div><small>Verifier</small><strong>{teamProject.verifier_email}</strong></div>
                    {/* FIXED APPROVED BOX */}
                    <div>
                      <small>Blockchain</small>
                      {teamProject.blockchain_tx_hash? (
                        <div>
                          <strong style={{color:"#22c55e"}}>RECORDED</strong>
                          <div style={{fontSize:"10px", wordBreak:"break-all", marginTop:"4px", color:"#9ca3af"}}>
                            {teamProject.blockchain_tx_hash}
                          </div>
                          <a href={`https://sepolia.etherscan.io/tx/${teamProject.blockchain_tx_hash.startsWith("0x")? teamProject.blockchain_tx_hash : "0x"+teamProject.blockchain_tx_hash}`} target="_blank" rel="noreferrer" style={{fontSize:"11px", color:"#60a5fa", textDecoration:"underline"}}>
                            View on Etherscan →
                          </a>
                          <div style={{fontSize:"10px", color:"#6b7280"}}>Block: {teamProject.blockchain_block_number || "—"} | {teamProject.blockchain_status}</div>
                        </div>
                      ) : (
                        <strong>{teamProject.blockchain_status === "CONFIRMED"? "RECORDED" : "PENDING"}</strong>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {teamProject.status === "NOT_APPROVED" && (
                <div className="rejectionBox">
                  <h3>✕ PROJECT NOT APPROVED</h3>
                  <p>The verification team did not approve this project.</p>
                  <div className="mail">Remarks:<b> {teamProject.verifier_remarks}</b></div>
                </div>
              )}
              {teamMessage && <div className="mail">✓ {teamMessage}</div>}
            </div>
          )}
        </section>
      </main>
    );
  }

  if (page === "reverify") {
    return (
      <main className="app">
        <aside>
          <div className="brand"><span>◈</span> CARBON<span>VAULT</span></div>
          <button className="nav" onClick={() => setPage("dashboard")}>⌂ Dashboard</button>
          <button className="nav" onClick={() => setPage("verify")}>＋ New Verification</button>
          <button className="nav" onClick={() => setPage("team")}>✓ Team Verification</button>
          <button className="nav active">↻ Reverification</button>
          <div className="sideBottom">VERIFICATION TEAM<br /><b>carbonvault26@gmail.com</b></div>
        </aside>
        <section className="content">
          <header><div><p className="eyebrow">CARBON VAULT / MONITORING</p><h2>Automatic Reverification</h2></div><div className="avatar">{form.userId?.[0]?.toUpperCase() || "U"}</div></header>
          <div className="notice"><span>●</span><div><b>Sentinel-2 monitoring comparison</b><p>CarbonVault automatically retrieves a new Sentinel-2 image, calculates NDVI, compares it with the original baseline and checks for vegetation loss.</p></div></div>
          <div className="card">
            <h3>Run Reverification</h3><p className="muted">The backend retrieves the latest Sentinel-2 data automatically. No satellite image upload is needed.</p>
            <label>Project ID<input value={reverifyProjectId} onChange={(e) => setReverifyProjectId(e.target.value)} placeholder="CV-PROJ-001" /></label>
            <button className="fetch" onClick={runReverification} disabled={reverifyLoading}>{reverifyLoading? "Fetching new Sentinel-2 data..." : "Run Automatic Reverification →"}</button>
          </div>
          {reverifyResult && (
            <div className="result">
              <div className={reverifyResult.flag === "RED_FLAG"? "status redFlag" : "status greenFlag"}>{reverifyResult.flag === "RED_FLAG"? "🔴 RED FLAG" : "🟢 GREEN FLAG"}</div>
              <h3>Reverification Analysis</h3>
              <div className="metrics">
                <div><small>Previous NDVI</small><strong>{Number(reverifyResult.previous_ndvi || 0).toFixed(4)}</strong></div>
                <div><small>Current NDVI</small><strong>{Number(reverifyResult.current_ndvi || 0).toFixed(4)}</strong></div>
                <div><small>NDVI Change</small><strong>{Number(reverifyResult.ndvi_change_percent || 0).toFixed(2)}%</strong></div>
              </div>
              <div className="metrics">
                <div><small>Previous Green Area</small><strong>{Number(reverifyResult.previous_green_area || 0).toFixed(2)}%</strong></div>
                <div><small>Current Green Area</small><strong>{Number(reverifyResult.current_green_area || 0).toFixed(2)}%</strong></div>
                <div><small>Green Area Change</small><strong>{Number(reverifyResult.green_area_change_percent || 0).toFixed(2)}%</strong></div>
              </div>
              <div className="metrics">
                <div><small>Previous Carbon Estimate</small><strong>{Number(reverifyResult.previous_carbon_estimate || 0).toFixed(2)}</strong></div>
                <div><small>Current Carbon Estimate</small><strong>{Number(reverifyResult.current_carbon_estimate || 0).toFixed(2)}</strong></div>
                <div><small>Carbon Change</small><strong>{Number(reverifyResult.carbon_change_percent || 0).toFixed(2)}%</strong></div>
              </div>
              <div className="mail"><b>Analysis:</b> {reverifyResult.message}</div>
              {reverifyResult.flag === "RED_FLAG" && <div className="rejectionBox"><h3>🔴 Physical Verification Required</h3><p>Anomaly detected in the latest Sentinel-2 comparison. The project owner and verification team have been notified for physical inspection.</p></div>}
              {reverifyResult.flag === "GREEN_FLAG" && <div className="approvalBox"><h3>🟢 NO SIGNIFICANT ANOMALY</h3><p>The latest satellite analysis did not detect a significant vegetation decrease relative to the baseline.</p></div>}
            </div>
          )}
          {error && <div className="error">{error}</div>}
        </section>
      </main>
    );
  }

  if (page === "verify") {
    return (
      <main className="app">
        <aside>
          <div className="brand"><span>◈</span> CARBON<span>VAULT</span></div>
          <button className="nav" onClick={() => setPage("dashboard")}>⌂ Dashboard</button>
          <button className="nav active">＋ New Verification</button>
          <button className="nav" onClick={() => setPage("team")}>✓ Team Verification</button>
          <button className="nav" onClick={() => setPage("reverify")}>↻ Reverification</button>
          <div className="sideBottom">VERIFICATION TEAM<br /><b>carbonvault26@gmail.com</b></div>
        </aside>
        <section className="content">
          <header><div><p className="eyebrow">CARBON VAULT / PROJECTS</p><h2>New Project Verification</h2></div><div className="avatar">{form.userId?.[0]?.toUpperCase() || "U"}</div></header>
          <div className="notice"><span>●</span><div><b>Team approval required</b><p>Satellite analysis is evidence only. Final approval is performed after physical inspection.</p></div></div>
          <div className="card">
            <h3>Project Details</h3>
            <div className="grid">
              <label>Project ID<input value={project.project_id} onChange={(e) => updateProject("project_id", e.target.value)} placeholder="CV-PROJ-001" /></label>
              <label>Company Name<input value={project.company_name} onChange={(e) => updateProject("company_name", e.target.value)} placeholder="Your company" /></label>
            </div>
            <div className="grid">
              <label>Project Location<input value={project.location} onChange={(e) => updateProject("location", e.target.value)} placeholder="Project location" /></label>
              <label>Project Area<input value={project.area} onChange={(e) => updateProject("area", e.target.value)} placeholder="Area in hectares" /></label>
            </div>
            <label>Project Owner Email<input type="email" value={project.user_email || form.email} onChange={(e) => updateProject("user_email", e.target.value)} placeholder="owner@example.com" /></label>
            <label>Project Bounding Box<span className="hint">minLon,minLat,maxLon,maxLat</span><input value={project.bbox} onChange={(e) => updateProject("bbox", e.target.value)} placeholder="78.08,9.90,78.13,9.95" /></label>
            <div className="grid">
              <label>From Date<input type="date" value={project.date_from} onChange={(e) => updateProject("date_from", e.target.value)} /></label>
              <label>To Date<input type="date" value={project.date_to} onChange={(e) => updateProject("date_to", e.target.value)} /></label>
            </div>
            <label>Satellite Image<span className="hint">optional reference upload</span><input type="file" accept="image/*,.tif,.tiff" onChange={(e) => updateProject("image", e.target.files?.[0] || null)} /></label>
            <button className="fetch" onClick={fetchSatellite} disabled={loading}>{loading? "Fetching real Sentinel-2 data..." : "Fetch Sentinel-2 Data →"}</button>
            {error && <div className="error">{error}</div>}
          </div>
          {result && (
            <div className="result">
              <div className="status">● PENDING TEAM VERIFICATION</div>
              <h3>Satellite Evidence Retrieved</h3>
              <div className="metrics">
                <div><small>Mean NDVI</small><strong>{Number(result.ndvi.mean).toFixed(4)}</strong></div>
                <div><small>Green Area</small><strong>{Number(result.ndvi.green_area_percent).toFixed(2)}%</strong></div>
                <div><small>SHA-256</small><strong>{result.satellite_data_sha256?.slice(0, 18)}…</strong></div>
              </div>
              <div className="metrics">
                <div><small>Blockchain</small><strong>{result.blockchain?.status === "CONFIRMED"? "RECORDED" : "PENDING"}</strong><div style={{fontSize:"9px", wordBreak:"break-all"}}>{result.blockchain?.tx_hash || ""}</div></div>
                <div><small>Email</small><strong>{result.email?.user?.status}</strong></div>
                <div><small>Status</small><strong>PENDING</strong></div>
              </div>
              <p>Sentinel-2 analysis completed. Physical team inspection is required before final approval.</p>
              <div className="mail">✉ Team notification:<b> {result.team_email}</b></div>
              <button className="fetch" onClick={() => setPage("team")}>Open Team Verification →</button>
            </div>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="app">
      <aside>
        <div className="brand"><span>◈</span> CARBON<span>VAULT</span></div>
        <button className="nav active">⌂ Dashboard</button>
        <button className="nav" onClick={() => setPage("verify")}>＋ New Verification</button>
        <button className="nav" onClick={() => setPage("team")}>✓ Team Verification</button>
        <button className="nav" onClick={() => setPage("reverify")}>↻ Reverification</button>
        <div className="sideBottom">VERIFICATION TEAM<br /><b>carbonvault26@gmail.com</b></div>
      </aside>
      <section className="content">
        <header><div><p className="eyebrow">CARBON VAULT / DASHBOARD</p><h2>Verification Dashboard</h2></div><div className="avatar">{form.userId?.[0]?.toUpperCase() || "U"}</div></header>
        <div className="notice"><span>●</span><div><b>Human-led carbon verification</b><p>Satellite evidence supports verification. Physical inspection determines final approval. Six-month monitoring compares new Sentinel-2 data against the original baseline.</p></div></div>
        {dashboardLoading? <div className="card">Loading dashboard...</div> : dashboard? (
          <>
            <div className="metrics dashboardMetrics">
              <div><small>Total Projects</small><strong>{dashboard.summary.total_projects}</strong></div>
              <div><small>Approved</small><strong>{dashboard.summary.approved_projects}</strong></div>
              <div><small>Pending</small><strong>{dashboard.summary.pending_projects}</strong></div>
              <div><small>Red Flags</small><strong>{dashboard.summary.red_flag_projects || 0}</strong></div>
            </div>
            <div className="card">
              <h3>Projects</h3>
              {dashboard.projects.length === 0? <p className="muted">No projects submitted yet.</p> : (
                <div className="projectTable">
                  {dashboard.projects.map((p) => (
                    <div className="projectRow" key={`${p.company_name}-${p.project_id}`}>
                      <div><small>PROJECT</small><b>{p.project_id}</b></div>
                      <div><small>COMPANY</small><b>{p.company_name || "—"}</b></div>
                      <div><small>NDVI</small><b>{Number(p.mean_ndvi || 0).toFixed(4)}</b></div>
                      <div><small>STATUS</small><b>{p.status}</b></div>
                      <div><small>MONITORING</small><b>{p.reverification_status || "NOT DUE"}</b></div>
                      <button className="smallButton" onClick={() => { setTeamProjectId(p.project_id); setPage("team"); }}>View</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="card"><h3>Six-Month Monitoring</h3><p className="muted">CarbonVault compares the new Sentinel-2 observation with the original baseline automatically.</p></div>
          </>
        ) : <div className="card"><h3>Dashboard unavailable</h3><button className="fetch" onClick={loadDashboard}>Refresh Dashboard</button></div>}
        {error && <div className="error">{error}</div>}
      </section>
    </main>
  );
}