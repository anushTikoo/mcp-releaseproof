import React from "react";
import { HealthStatus } from "./components/HealthStatus";
import { TestPlanGenerator } from "./components/TestPlanGenerator";
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

        <TestPlanGenerator />

        <section className="info-card">
          <h4>Platform Status & Milestone Tracker</h4>
          <p>
            Established clean local foundation and Vultr Serverless Inference planning integration.
          </p>
          <ul className="phase-list">
            <li className="phase-item">
              <span className="check-icon">✓</span> Phase 1: FastAPI control plane + React frontend + health probes
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> Phase 2: Vultr Serverless Inference client (Qwen 3.8 Flash Next)
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> Phase 2: Defensive prompt fencing & strict Pydantic TestPlan validation
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> Phase 2: Model fallback detection & error containment
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
};

export default App;

