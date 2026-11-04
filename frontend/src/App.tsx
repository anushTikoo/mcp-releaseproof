import React from "react";
import { HealthStatus } from "./components/HealthStatus";
import "./App.css";

export const App: React.FC = () => {
  return (
    <div className="app-container">
      <header className="app-header">
        <span className="brand-badge">MCP ReleaseProof</span>
        <h1 className="app-title">Release Verification Platform</h1>
        <p className="app-tagline">
          AI-assisted, sandboxed release verification for Model Context Protocol servers.
        </p>
      </header>

      <main className="main-content">
        <HealthStatus />

        <section className="info-card">
          <h4>Phase 1: Local Foundation Status</h4>
          <p>
            Established clean development foundation separating the React/Vite/TypeScript frontend
            and the FastAPI control-plane backend.
          </p>
          <ul className="phase-list">
            <li className="phase-item">
              <span className="check-icon">✓</span> FastAPI control plane with typed Pydantic settings
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> Health endpoints (/api/health and /health)
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> React frontend with live backend connectivity display
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> CORS configured between frontend (5173) and backend (8000)
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
};

export default App;

