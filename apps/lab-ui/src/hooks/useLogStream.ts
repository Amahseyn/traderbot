/**
 * useLogStream Hook — Real-time log viewing via WebSocket
 *
 * Features:
 * - Live log streaming
 * - Filtering by level, module, source
 * - Auto-scroll to latest
 * - Pause/resume
 */

import { useEffect, useState, useRef, useCallback } from "react";
import { API_BASE } from "@/lib/api";

export interface LogEntry {
  timestamp: number;
  timestamp_iso: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  module: string;
  message: string;
  context: Record<string, unknown>;
  source: string;
}

export interface UseLogStreamOptions {
  level?: string;
  module?: string;
  source?: string;
  maxLogs?: number;
  autoScroll?: boolean;
}

export function useLogStream(options: UseLogStreamOptions = {}) {
  const {
    level,
    module,
    source,
    maxLogs = 500,
    autoScroll = true,
  } = options;

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [paused, setPaused] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(() => {
    const wsUrl = `${API_BASE.replace("http", "ws")}/ws/logs`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      // Send initial filter
      if (level || module || source) {
        ws.send(JSON.stringify({ level, module, source }));
      }
    };

    ws.onmessage = (event) => {
      if (paused) return;

      try {
        const entry: LogEntry = JSON.parse(event.data);
        setLogs((prev) => {
          const updated = [...prev, entry];
          return updated.slice(-maxLogs);
        });
      } catch (err) {
        console.error("Failed to parse log entry:", err);
      }
    };

    ws.onerror = (err) => {
      setError("WebSocket connection error");
      setConnected(false);
    };

    ws.onclose = () => {
      setConnected(false);
      // Attempt reconnect after delay
      setTimeout(connect, 5000);
    };

    wsRef.current = ws;
  }, [level, module, source, paused, maxLogs]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const clear = useCallback(() => {
    setLogs([]);
  }, []);

  const downloadLogs = useCallback(async (format: "json" | "csv" | "txt" = "json") => {
    try {
      const params = new URLSearchParams();
      params.append("format", format);
      if (level) params.append("level", level);
      if (source) params.append("source", source);

      const response = await fetch(`${API_BASE}/api/logs/export?${params}`);
      if (!response.ok) throw new Error("Download failed");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `logs.${format === "json" ? "json" : format === "csv" ? "csv" : "txt"}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Download failed:", err);
    }
  }, [level, source]);

  return {
    logs,
    connected,
    error,
    paused,
    setPaused,
    clear,
    downloadLogs,
  };
}
