"use client";

import { useEffect, useState } from "react";
import Sidebar from "./Sidebar";
import { apiFetch, type CameraStats } from "../../lib/api";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [stats, setStats] = useState<CameraStats | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const s = await apiFetch<CameraStats>("/camera/stats");
        if (alive) setStats(s);
      } catch {
        if (alive) setStats(null);
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const online = Boolean(stats?.camera_opened && stats.running);

  return (
    <div className="app-root">
      <div className="app-frame">
        <Sidebar cameraOnline={online} lastInferenceMs={stats?.last_inference_ms ?? null} />
        <main className="main-area">{children}</main>
      </div>
      <style jsx>{`
        .app-root {
          min-height: 100vh;
          background: var(--bg);
          padding: 8px;
        }
        .app-frame {
          display: flex;
          min-height: calc(100vh - 16px);
          border: 1px solid var(--border-solid);
          border-radius: 4px;
          overflow: hidden;
          background: var(--bg);
        }
        .main-area {
          flex: 1;
          display: flex;
          flex-direction: column;
          min-width: 0;
          overflow-y: auto;
        }
      `}</style>
    </div>
  );
}
