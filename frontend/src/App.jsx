import { useEffect, useState } from "react";

function App() {
  const [pack, setPack] = useState(null);
  const [appMap, setAppMap] = useState(null);
  const [loading, setLoading] = useState(true);
  const [isEmpty, setIsEmpty] = useState(false);
  const [error, setError] = useState("");

  const [refreshCount, setRefreshCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const packResponse = await fetch("/api/knowledge-pack/latest");

        if (cancelled) return;

        if (packResponse.status === 404) {
          setIsEmpty(true);
          setPack(null);
          setAppMap(null);
          return;
        }

        if (!packResponse.ok) {
          throw new Error(`Could not load Knowledge Pack (HTTP ${packResponse.status})`);
        }

        const packData = await packResponse.json();
        if (cancelled) return;
        setPack(packData);

        const scanId = packData.scan_id;
        const mapUrl = scanId
          ? `/api/app-map?scan_id=${encodeURIComponent(scanId)}`
          : "/api/app-map";

        const mapResponse = await fetch(mapUrl);
        if (cancelled) return;

        if (!mapResponse.ok) {
          throw new Error(`Could not load App Map (HTTP ${mapResponse.status})`);
        }

        const mapData = await mapResponse.json();
        if (cancelled) return;
        setAppMap(mapData);
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Failed to load data from Knowledge Engine.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [refreshCount]);

  const handleRefresh = () => {
    setLoading(true);
    setError("");
    setIsEmpty(false);
    setRefreshCount((c) => c + 1);
  };

  if (loading) {
    return (
      <div style={{ padding: "40px", fontFamily: "Arial" }}>
        <h1>REV RAG AI</h1>
        <h2>Loading Knowledge Engine...</h2>
      </div>
    );
  }

  if (isEmpty) {
    return (
      <div style={{ padding: "40px", fontFamily: "Arial", background: "#f5f7fa", minHeight: "100vh" }}>
        <h1>REV RAG AI</h1>
        <p>Autonomous Android App Exploration Dashboard</p>
        <hr />
        <div
          style={{
            background: "white",
            padding: "30px",
            borderRadius: "10px",
            marginTop: "20px",
            border: "1px solid #e2e8f0",
          }}
        >
          <h2 style={{ color: "#4a5568" }}>No Knowledge Pack generated yet. Run an exploration first.</h2>
          <p style={{ color: "#718096" }}>
            The Knowledge Engine has not detected any completed exploration runs. Start autonomous exploration to generate screens, actions, transitions, journeys, and an App Map.
          </p>
          <button
            onClick={handleRefresh}
            style={{
              marginTop: "10px",
              padding: "10px 20px",
              background: "#3182ce",
              color: "white",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontWeight: "bold",
            }}
          >
            Check Again
          </button>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: "40px", fontFamily: "Arial", background: "#f5f7fa", minHeight: "100vh" }}>
        <h1>REV RAG AI</h1>
        <h2>Backend Connection Error</h2>
        <p style={{ color: "#e53e3e" }}>{error}</p>
        <button
          onClick={handleRefresh}
          style={{
            marginTop: "10px",
            padding: "10px 20px",
            background: "#3182ce",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  const screens = pack?.screens || [];
  const actions = pack?.actions || [];
  const transitions = pack?.transitions || [];
  const journeys = pack?.journeys || [];
  const warnings = pack?.warnings || [];

  return (
    <div
      style={{
        padding: "40px",
        fontFamily: "Arial",
        background: "#f5f7fa",
        minHeight: "100vh",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1>REV RAG AI</h1>
          <p>Autonomous Android App Exploration Dashboard</p>
          {pack?.scan_id && (
            <p style={{ color: "#718096", fontSize: "14px" }}>
              Scan ID: <strong>{pack.scan_id}</strong> | Package: <strong>{pack.app?.package_name || "N/A"}</strong> | Pack ID: <strong>{pack.pack_id}</strong>
            </p>
          )}
        </div>
        <button
          onClick={handleRefresh}
          style={{
            padding: "8px 16px",
            background: "#3182ce",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: "pointer",
            fontWeight: "bold",
          }}
        >
          Refresh Data
        </button>
      </div>

      <hr />

      <h2>Exploration Statistics</h2>

      <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
        <StatCard title="Screens" value={screens.length} />
        <StatCard title="Actions" value={actions.length} />
        <StatCard title="Transitions" value={transitions.length} />
        <StatCard title="Journeys" value={journeys.length} />
        {pack?.statistics?.element_count !== undefined && (
          <StatCard title="Elements" value={pack.statistics.element_count} />
        )}
      </div>

      {warnings.length > 0 && (
        <>
          <h2>Warnings ({warnings.length})</h2>
          <div
            style={{
              background: "#fffaf0",
              border: "1px solid #fbd38d",
              borderRadius: "10px",
              padding: "16px",
            }}
          >
            <ul style={{ margin: 0, paddingLeft: "20px", color: "#c05621" }}>
              {warnings.map((w, idx) => (
                <li key={idx}>{w}</li>
              ))}
            </ul>
          </div>
        </>
      )}

      <h2>App Map</h2>

      <pre
        style={{
          background: "white",
          padding: "20px",
          borderRadius: "10px",
          overflow: "auto",
        }}
      >
        {JSON.stringify(appMap, null, 2)}
      </pre>

      <h2>Screens</h2>

      <pre
        style={{
          background: "white",
          padding: "20px",
          borderRadius: "10px",
          overflow: "auto",
        }}
      >
        {JSON.stringify(screens, null, 2)}
      </pre>

      <h2>Actions</h2>

      <pre
        style={{
          background: "white",
          padding: "20px",
          borderRadius: "10px",
          overflow: "auto",
        }}
      >
        {JSON.stringify(actions, null, 2)}
      </pre>

      <h2>Transitions</h2>

      <pre
        style={{
          background: "white",
          padding: "20px",
          borderRadius: "10px",
          overflow: "auto",
        }}
      >
        {JSON.stringify(transitions, null, 2)}
      </pre>

      <h2>Journeys</h2>

      <pre
        style={{
          background: "white",
          padding: "20px",
          borderRadius: "10px",
          overflow: "auto",
        }}
      >
        {JSON.stringify(journeys, null, 2)}
      </pre>

      <h2>Design Language</h2>

      <pre
        style={{
          background: "white",
          padding: "20px",
          borderRadius: "10px",
          overflow: "auto",
        }}
      >
        {JSON.stringify(pack?.design_language, null, 2)}
      </pre>
    </div>
  );
}

function StatCard({ title, value }) {
  return (
    <div
      style={{
        background: "white",
        padding: "20px",
        borderRadius: "10px",
        minWidth: "130px",
      }}
    >
      <h3>{title}</h3>

      <div style={{ fontSize: "32px", fontWeight: "bold" }}>{value}</div>
    </div>
  );
}

export default App;
