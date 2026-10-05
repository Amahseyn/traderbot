/**
 * JobLogs Component — Real-time logs for a specific job
 *
 * Shows logs filtered to a specific job_id, with live streaming.
 * Used in job monitoring UI (Data, Actions, Experiments sections).
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { useLogs } from "@/hooks/useLogs";

export interface JobLogsProps {
  jobId: string;
  initialLoad?: boolean;
}

export function JobLogs({ jobId, initialLoad = true }: JobLogsProps) {
  const { logs, loading, fetchRecent } = useLogs();
  const [autoRefresh, setAutoRefresh] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Initial load and polling
  useEffect(() => {
    if (initialLoad) {
      fetchRecent(500, undefined, undefined, jobId);
    }

    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchRecent(500, undefined, undefined, jobId);
      }, 2000);

      return () => clearInterval(interval);
    }
  }, [jobId, autoRefresh, initialLoad, fetchRecent]);

  // Auto-scroll
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const getLevelBg = (level: string) => {
    switch (level) {
      case "ERROR":
      case "CRITICAL":
        return "bg-red-50 border-l-4 border-red-500";
      case "WARNING":
        return "bg-yellow-50 border-l-4 border-yellow-500";
      case "INFO":
        return "bg-blue-50 border-l-4 border-blue-500";
      default:
        return "bg-gray-50";
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case "DEBUG":
        return "text-gray-500";
      case "INFO":
        return "text-blue-600 font-semibold";
      case "WARNING":
        return "text-yellow-600 font-semibold";
      case "ERROR":
        return "text-red-600 font-bold";
      case "CRITICAL":
        return "text-red-700 font-bold";
      default:
        return "text-gray-700";
    }
  };

  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="bg-gray-100 px-4 py-3 flex justify-between items-center border-b">
        <div>
          <h3 className="font-semibold text-gray-900">Job Logs</h3>
          <p className="text-xs text-gray-600 mt-1">Job ID: {jobId}</p>
        </div>
        <button
          onClick={() => setAutoRefresh(!autoRefresh)}
          className={`px-3 py-1 rounded text-xs font-semibold transition ${
            autoRefresh
              ? "bg-green-600 text-white"
              : "bg-gray-300 text-gray-700"
          }`}
        >
          {autoRefresh ? "Live" : "Paused"}
        </button>
      </div>

      {/* Logs */}
      <div className="h-80 overflow-y-auto font-mono text-sm space-y-1 p-4">
        {logs.length === 0 ? (
          <div className="text-center text-gray-400 py-20">
            {loading ? "Loading logs..." : "No logs yet"}
          </div>
        ) : (
          logs.map((log, idx) => (
            <div
              key={idx}
              className={`px-3 py-2 rounded ${getLevelBg(log.level)}`}
            >
              <div className="flex gap-2">
                <span className="text-gray-500 flex-shrink-0 w-32">
                  {new Date(log.timestamp_iso).toLocaleTimeString()}
                </span>
                <span className={`flex-shrink-0 w-12 ${getLevelColor(log.level)}`}>
                  {log.level}
                </span>
                <span className="text-gray-600 flex-shrink-0 w-40">
                  {log.module.split(".").pop()}
                </span>
                <span className="flex-1 text-gray-800">{log.message}</span>
              </div>
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>

      {/* Footer stats */}
      <div className="bg-gray-50 px-4 py-2 border-t text-xs text-gray-600 flex justify-between">
        <span>Showing {logs.length} logs</span>
        <span>{loading ? "Updating..." : "Up to date"}</span>
      </div>
    </div>
  );
}
