/**
 * ML Model Discovery & Prediction Component
 *
 * Displays available models, horizons, and allows users to:
 * - Select model, horizon, symbol
 * - Input features
 * - Run predictions
 * - See results in real-time
 */

"use client";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";

interface ModelInfo {
  model_id: string;
  supports_streaming: boolean;
  info: Record<string, unknown>;
}

interface Horizon {
  value: number;
  unit: string;
  label: string;
  minutes: number;
}

interface Prediction {
  value: number;
  confidence: number;
  forecast_kind: string;
  model_id: string;
  horizon_label: string;
  timestamp_utc: number;
  metadata: Record<string, unknown>;
}

export function MLModelBrowser() {
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [horizons, setHorizons] = useState<Horizon[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [selectedHorizon, setSelectedHorizon] = useState<string>("");
  const [symbol, setSymbol] = useState("BTC");
  const [features, setFeatures] = useState<Record<string, number>>({});
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load models and horizons
  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [modelsRes, horizonsRes] = await Promise.all([
          fetch(`${API_BASE}/api/ml/models`),
          fetch(`${API_BASE}/api/ml/horizons`),
        ]);

        if (!modelsRes.ok || !horizonsRes.ok) throw new Error("Failed to load options");

        const modelsData = await modelsRes.json();
        const horizonsData = await horizonsRes.json();

        // Fetch details for each model
        const modelDetails = await Promise.all(
          modelsData.models.map((id: string) =>
            fetch(`${API_BASE}/api/ml/models/${id}`).then((r) => r.json())
          )
        );

        setModels(modelDetails);
        setHorizons(horizonsData.horizons);

        if (modelDetails.length > 0) {
          setSelectedModel(modelDetails[0].model_id);
        }
        if (horizonsData.horizons.length > 0) {
          setSelectedHorizon(horizonsData.horizons[0].label);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    };

    loadOptions();
  }, []);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/ml/predict`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model_id: selectedModel,
          horizon_label: selectedHorizon,
          symbol,
          features,
        }),
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const pred = await res.json();
      setPrediction(pred);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">ML Model Browser</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Model Selection */}
        <div>
          <label className="block text-sm font-medium mb-2">Model</label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="w-full border rounded px-3 py-2"
          >
            {models.map((m) => (
              <option key={m.model_id} value={m.model_id}>
                {m.model_id}
                {m.supports_streaming ? " (streaming)" : ""}
              </option>
            ))}
          </select>
        </div>

        {/* Horizon Selection */}
        <div>
          <label className="block text-sm font-medium mb-2">Horizon</label>
          <select
            value={selectedHorizon}
            onChange={(e) => setSelectedHorizon(e.target.value)}
            className="w-full border rounded px-3 py-2"
          >
            {horizons.map((h) => (
              <option key={h.label} value={h.label}>
                {h.label} ({h.minutes} min)
              </option>
            ))}
          </select>
        </div>

        {/* Symbol */}
        <div>
          <label className="block text-sm font-medium mb-2">Symbol</label>
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="w-full border rounded px-3 py-2"
            placeholder="BTC, ETH, etc."
          />
        </div>
      </div>

      {/* Features Input */}
      <div>
        <label className="block text-sm font-medium mb-2">Features (JSON)</label>
        <textarea
          value={JSON.stringify(features, null, 2)}
          onChange={(e) => {
            try {
              setFeatures(JSON.parse(e.target.value));
            } catch {
              // Ignore parse errors while typing
            }
          }}
          className="w-full border rounded px-3 py-2 font-mono text-sm h-32"
          placeholder='{"rsi_14": 35, "sma_20": 42000, ...}'
        />
      </div>

      {/* Predict Button */}
      <button
        onClick={handlePredict}
        disabled={loading}
        className="w-full bg-blue-600 text-white py-2 rounded font-semibold hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? "Predicting..." : "Predict"}
      </button>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded p-4 text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {prediction && (
        <div className="bg-green-50 border border-green-200 rounded p-6 space-y-3">
          <h3 className="font-bold text-green-900">Prediction Result</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <span className="text-sm text-gray-600">Value</span>
              <p className="text-xl font-mono">
                {prediction.value.toFixed(6)}
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">Confidence</span>
              <p className="text-xl font-mono">
                {(prediction.confidence * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <span className="text-sm text-gray-600">Forecast Kind</span>
              <p className="text-sm">{prediction.forecast_kind}</p>
            </div>
            <div>
              <span className="text-sm text-gray-600">Horizon</span>
              <p className="text-sm">{prediction.horizon_label}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
