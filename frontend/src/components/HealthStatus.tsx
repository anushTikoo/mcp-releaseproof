import React, { useEffect, useState } from "react";
import { API_BASE_URL, fetchHealth, HealthStatusResponse } from "../api/client";

export const HealthStatus: React.FC = () => {
  const [health, setHealth] = useState<HealthStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHealth();
      setHealth(data);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unknown error occurred while contacting the backend.");
      }
      setHealth(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((data) => {
        setHealth(data);
        setError(null);
      })
      .catch((err: unknown) => {
        if (err instanceof Error && err.name === "AbortError") {
          return;
        }
        setError(
          err instanceof Error
            ? err.message
            : "Failed to connect to backend service"
        );
        setHealth(null);
      })
      .finally(() => {
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, []);

  return (
    <div className="health-card" data-testid="health-status-card">
      <div className="health-header">
        <h3 className="health-title">Backend Control-Plane Status</h3>
        <button
          className="refresh-btn"
          onClick={checkHealth}
          disabled={loading}
          aria-label="Recheck backend health"
        >
          {loading ? "Checking..." : "Recheck"}
        </button>
      </div>

      <div className="health-endpoint">
        <span className="label">Endpoint:</span>
        <code className="endpoint-code">{`${API_BASE_URL.replace(
          /\/+$/,
          ""
        )}/health`}</code>
      </div>

      <div className="health-body">
        {loading && !health && (
          <div className="status-indicator loading" data-testid="status-loading">
            <span className="dot pulse"></span>
            <span>Connecting to backend...</span>
          </div>
        )}

        {error && (
          <div className="status-indicator error" data-testid="status-error">
            <span className="dot red"></span>
            <div>
              <strong>Connectivity Error:</strong>
              <p className="error-message">{error}</p>
            </div>
          </div>
        )}

        {health && (
          <div className="status-indicator ok" data-testid="status-ok">
            <span className="dot green"></span>
            <div className="details-grid">
              <div>
                <strong>Status:</strong> {health.status}
              </div>
              <div>
                <strong>Application:</strong> {health.app}
              </div>
              <div>
                <strong>Version:</strong> {health.version}
              </div>
              <div>
                <strong>Server UTC:</strong> {health.timestamp}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

