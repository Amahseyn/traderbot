/**
 * LogViewer Component — Comprehensive log viewing UI
 *
 * Features:
 * - Real-time log streaming
 * - Filtering by level, module, source
 * - Full-text search
 * - Export (JSON, CSV, TXT)
 * - Auto-scroll with pause
 * - Color-coded log levels
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { useLogStream } from "@/hooks/useLogStream";
import { useLogs } from "@/hooks/useLogs";

export function LogViewer() {
  const { logs, connected, error, paused, setPaused, clear, downloadLogs } =
    useLogStream({ maxLogs: 1000 });

  const { logs: searchLogs, search, loading: searching } = useLogs();
  const { stats, fetchStats } = useLogs();

  const [mode, setMode] = useState<"stream" | "search">("stream");
  const [searchQuery, setSearchQuery] = useState("");
  const [filterLevel, setFilterLevel] = useState<string>("");
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (!paused && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, paused]);

  // Fetch stats on mount
  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      await search(searchQuery);
      setMode("search");
    }
  };

  const currentLogs = mode === "stream" ? logs : searchLogs;
  const displayedLogs = filterLevel
    ? currentLogs.filter((log) => log.level === filterLevel)
    : currentLogs;

  const getLevelColor = (level: string) => {
    switch (level) {
      case "DEBUG":
        return "text-gray-500";
      case "INFO":
        return "text-blue-600";
      case "WARNING":
        return "text-yellow-600";
      case "ERROR":
        return "text-red-600";
      case "CRITICAL":
        return "text-red-800 bg-red-100";
      default:
        return "text-gray-700";
    }
  };

  const getLevelBg = (level: string) => {
    switch (level) {
      case "CRITICAL":
        return "bg-red-50";
      case "ERROR":
        return "bg-red-50";
      case "WARNING":
        return "bg-yellow-50";
      default:
        return "bg-white";
    }
  };

  return (
    <div className="space-y-4 bg-gray-50 rounded-lg p-6">
      <div className="space-y-4">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-2xl font-bold">Logs</h2>
            <div className="text-xs text-gray-600 mt-1">
              {connected ? (
                <span className="text-green-600">● Live streaming</span>
              ) : (
                <span className="text-red-600">● Disconnected</span>
              )}
              {error && <span className="text-red-600 ml-2">{error}</span>}
            </div>
          </div>
          <div className="text-right">
            {stats && (
              <div className="text-sm text-gray-600">
                <div>Total: {stats.total} entries</div>
                <div>Time span: {Math.round(stats.time_span_seconds)}s</div>
              </div>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="space-y-3 bg-white p-4 rounded border">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex gap-2">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search logs..."
              className="flex-1 px-3 py-2 border rounded text-sm"
            />
            <button
              type="submit"
              disabled={searching}
              className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-semibold hover:bg-blue-700 disabled:opacity-50"
            >
              {searching ? "Searching..." : "Search"}
            </button>
          </form>

          {/* Filters & Actions */}
          <div className="flex gap-2 flex-wrap items-center">
            {/* Mode toggle */}
            <div className="flex gap-1">
              <button
                onClick={() => setMode("stream")}
                className={`px-3 py-1 rounded text-xs font-semibold ${
                  mode === "stream"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-200 text-gray-700"
                }`}
              >
                Stream
              </button>
              <button
                onClick={() => setMode("search")}
                className={`px-3 py-1 rounded text-xs font-semibold ${
                  mode === "search"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-200 text-gray-700"
                }`}
              >
                Search
              </button>
            </div>

            {/* Level filter */}
            <select
              value={filterLevel}
              onChange={(e) => setFilterLevel(e.target.value)}
              className="px-3 py-1 border rounded text-xs"
            >
              <option value="">All levels</option>
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>

            {/* Pause button */}
            {mode === "stream" && (
              <button
                onClick={() => setPaused(!paused)}
                className={`px-3 py-1 rounded text-xs font-semibold ${
                  paused
                    ? "bg-orange-600 text-white"
                    : "bg-gray-200 text-gray-700"
                }`}
              >
                {paused ? "Resume" : "Pause"}
              </button>
            )}

            {/* Clear button */}
            <button
              onClick={clear}
              className="px-3 py-1 bg-gray-200 text-gray-700 rounded text-xs font-semibold hover:bg-gray-300"
            >
              Clear
            </button>

            {/* Export */}
            <div className="flex gap-1">
              <button
                onClick={() => downloadLogs("json")}
                className="px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs hover:bg-gray-300"
              >
                JSON
              </button>
              <button
                onClick={() => downloadLogs("csv")}
                className="px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs hover:bg-gray-300"
              >
                CSV
              </button>
              <button
                onClick={() => downloadLogs("txt")}
                className="px-2 py-1 bg-gray-200 text-gray-700 rounded text-xs hover:bg-gray-300"
              >
                TXT
              </button>
            </div>

            {/* Stats */}
            {stats && (
              <div className="ml-auto text-xs text-gray-600">
                Showing {displayedLogs.length} of {stats.total}
              </div>
            )}
          </div>
        </div>

        {/* Log display */}
        <div className="bg-white border rounded h-96 overflow-y-auto font-mono text-xs">
          {displayedLogs.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              {mode === "stream"
                ? "Waiting for logs..."
                : "No search results"}
            </div>
          ) : (
            <table className="w-full border-collapse">
              <tbody>
                {displayedLogs.map((log, idx) => (
                  <tr key={idx} className={`border-b ${getLevelBg(log.level)}`}>
                    <td className="px-3 py-1 text-gray-600 w-40">
                      {new Date(log.timestamp_iso).toLocaleTimeString()}
                    </td>
                    <td className={`px-3 py-1 font-bold w-16 ${getLevelColor(log.level)}`}>
                      {log.level}
                    </td>
                    <td className="px-3 py-1 text-gray-600 w-40">
                      {log.module}
                    </td>
                    <td className="px-3 py-1 flex-1">
                      {log.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div ref={logsEndRef} />
        </div>

        {/* Level stats */}
        {stats?.by_level && (
          <div className="bg-white border rounded p-3 grid grid-cols-5 gap-3 text-center text-xs">
            {Object.entries(stats.by_level).map(([level, count]) => (
              <div key={level}>
                <div className="font-semibold text-gray-700">{level}</div>
                <div className={`text-lg font-bold ${getLevelColor(level)}`}>
                  {count}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
