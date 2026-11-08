import React, { useState } from "react";
import { HealthStatus } from "./components/HealthStatus";
import { GitHubComparator } from "./components/GitHubComparator";
import { MCPServerInspector } from "./components/MCPServerInspector";
import { TestPlanGenerator } from "./components/TestPlanGenerator";
import { TestHarnessGenerator } from "./components/TestHarnessGenerator";
import { DiscoveredToolInput, ExtractedTool, TestPlan } from "./api/client";
import "./App.css";

export const App: React.FC = () => {
  const [activeRepoUrl, setActiveRepoUrl] = useState<string>(
    "https://github.com/example/filesystem-mcp-server"
  );
  const [activeCommitSha] = useState<string>(
    "a1b2c3d4e5f67890123456789012345678901234"
  );
  const [activeRef] = useState<string>("v1.0.0");
  const [discoveredTools, setDiscoveredTools] = useState<DiscoveredToolInput[] | null>(
    null
  );
  const [generatedPlan, setGeneratedPlan] = useState<TestPlan | null>(null);

  const handleToolsExtracted = (tools: ExtractedTool[], repoUrl: string) => {
    setActiveRepoUrl(repoUrl);
    const converted: DiscoveredToolInput[] = tools.map((t) => ({
      tool_name: t.name,
      description: t.description || "",
      input_schema: t.input_schema || {},
    }));
    setDiscoveredTools(converted);
  };

  const handlePlanGenerated = (plan: TestPlan, repoUrl: string) => {
    setActiveRepoUrl(repoUrl);
    setGeneratedPlan(plan);
  };

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

        <GitHubComparator />

        <MCPServerInspector onToolsExtracted={handleToolsExtracted} />

        <TestPlanGenerator
          initialTools={discoveredTools}
          initialRepoUrl={activeRepoUrl}
          onPlanGenerated={handlePlanGenerated}
        />

        <TestHarnessGenerator
          discoveredTools={discoveredTools}
          testPlan={generatedPlan}
          repositoryUrl={activeRepoUrl}
          commitSha={activeCommitSha}
          refLabel={activeRef}
        />

        <section className="info-card">
          <h4>Platform Status & Milestone Tracker</h4>
          <p>
            Established clean local foundation, Vultr Serverless Inference planning, GitHub commit comparison, static MCP server tool/schema extraction, and AI test harness generation with AST security validation.
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
              <span className="check-icon">✓</span> Phase 3: GitHub repository validation, ref resolution & version comparison
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> Phase 4: Static MCP server discovery, tool/schema extraction & version diffing
            </li>
            <li className="phase-item">
              <span className="check-icon">✓</span> Phase 5: AI-generated executable test harness & static AST security validation
            </li>
          </ul>
        </section>
      </main>
    </div>
  );
};

export default App;
