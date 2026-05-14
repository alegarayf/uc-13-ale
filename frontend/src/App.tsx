import { useEffect, useState } from "react";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";
const aiBase = import.meta.env.VITE_AI_API_BASE_URL ?? "";

export default function App() {
  const [apiHealth, setApiHealth] = useState<string>("…");
  const [aiHealth, setAiHealth] = useState<string>("…");

  useEffect(() => {
    if (!apiBase) {
      setApiHealth("Set VITE_API_BASE_URL in root .env");
      return;
    }
    fetch(`${apiBase}/health`)
      .then((r) => r.json())
      .then((j) => setApiHealth(JSON.stringify(j)))
      .catch(() => setApiHealth("unreachable"));
  }, []);

  useEffect(() => {
    if (!aiBase) {
      setAiHealth("optional");
      return;
    }
    fetch(`${aiBase}/health`)
      .then((r) => r.json())
      .then((j) => setAiHealth(JSON.stringify(j)))
      .catch(() => setAiHealth("unreachable"));
  }, []);

  return (
    <main className="app">
      <h1>Rallyday</h1>
      <p>API: {apiHealth}</p>
      <p>AI: {aiHealth}</p>
    </main>
  );
}
