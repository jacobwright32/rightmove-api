import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Plot from "react-plotly.js";
import { getModelFeatures, predictPostcode, predictProperty, trainModel } from "../api/client";
import type {
  AvailableFeaturesResponse,
  FeatureImportance,
  FeatureInfo,
  PostcodePredictionItem,
  PredictionPoint,
  TrainResponse,
} from "../api/types";
import StatCard from "../components/StatCard";
import { useDarkMode } from "../hooks/useDarkMode";
import { getChartColors } from "../utils/chartTheme";

const PLOTLY_CONFIG = { responsive: true, displaylogo: false };

function usePlotlyTheme(dark: boolean) {
  return useMemo(() => ({
    text: dark ? "#d1d5db" : "#374151",
    grid: dark ? "#374151" : "#e5e7eb",
    bg: dark ? "#1f2937" : "#ffffff",
  }), [dark]);
}

export default function ModellingPage() {
  const dark = useDarkMode();
  const colors = getChartColors(dark);
  const theme = usePlotlyTheme(dark);

  // Feature metadata
  const [meta, setMeta] = useState<AvailableFeaturesResponse | null>(null);
  const [metaError, setMetaError] = useState("");

  // Config state
  const [target, setTarget] = useState("price_numeric");
  const [modelType, setModelType] = useState("lightgbm");
  const [splitStrategy, setSplitStrategy] = useState("random");
  const [testRatio, setTestRatio] = useState(0.2);
  const [cutoffDate, setCutoffDate] = useState("2024-01-01");
  const [selectedFeatures, setSelectedFeatures] = useState<Set<string>>(new Set());

  // Training state
  const [training, setTraining] = useState(false);
  const [trainError, setTrainError] = useState("");
  const [result, setResult] = useState<TrainResponse | null>(null);

  // Shared prediction date
  const [predictionDate, setPredictionDate] = useState(
    new Date().toISOString().split("T")[0],
  );

  // Prediction state
  const [predictId, setPredictId] = useState("");
  const [predicting, setPredicting] = useState(false);
  const [prediction, setPrediction] = useState<{ predicted_value: number; address: string } | null>(null);
  const [predictError, setPredictError] = useState("");

  // Postcode prediction state
  const [predictPostcodeVal, setPredictPostcodeVal] = useState("");
  const [postcodeLimit, setPostcodeLimit] = useState(50);
  const [predictingPostcode, setPredictingPostcode] = useState(false);
  const [postcodePredictions, setPostcodePredictions] = useState<PostcodePredictionItem[] | null>(null);
  const [postcodeError, setPostcodeError] = useState("");

  // Load features on mount
  useEffect(() => {
    getModelFeatures()
      .then((data) => {
        setMeta(data);
        setSelectedFeatures(new Set(data.features.map((f) => f.name)));
      })
      .catch((e) => setMetaError(e?.response?.data?.detail || "Failed to load features"));
  }, []);

  // Group features by category
  const grouped = useMemo(() => {
    if (!meta) return {};
    const groups: Record<string, FeatureInfo[]> = {};
    for (const f of meta.features) {
      (groups[f.category] ??= []).push(f);
    }
    return groups;
  }, [meta]);

  const toggleFeature = useCallback((name: string) => {
    setSelectedFeatures((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    if (meta) setSelectedFeatures(new Set(meta.features.map((f) => f.name)));
  }, [meta]);

  const deselectAll = useCallback(() => {
    setSelectedFeatures(new Set());
  }, []);

  const handleTrain = useCallback(async () => {
    setTraining(true);
    setTrainError("");
    setResult(null);
    setPrediction(null);
    try {
      const resp = await trainModel({
        target,
        features: [...selectedFeatures],
        model_type: modelType,
        split_strategy: splitStrategy,
        split_params: splitStrategy === "temporal"
          ? { cutoff_date: cutoffDate }
          : { test_ratio: testRatio },
      });
      setResult(resp);
    } catch (e: any) {
      setTrainError(e?.response?.data?.detail || "Training failed");
    } finally {
      setTraining(false);
    }
  }, [target, selectedFeatures, modelType, splitStrategy, cutoffDate, testRatio]);

  const handlePredict = useCallback(async () => {
    if (!result || !predictId) return;
    setPredicting(true);
    setPredictError("");
    setPrediction(null);
    try {
      const resp = await predictProperty(result.model_id, Number(predictId), predictionDate);
      setPrediction(resp);
    } catch (e: any) {
      setPredictError(e?.response?.data?.detail || "Prediction failed");
    } finally {
      setPredicting(false);
    }
  }, [result, predictId, predictionDate]);

  const handlePredictPostcode = useCallback(async () => {
    if (!result || !predictPostcodeVal) return;
    setPredictingPostcode(true);
    setPostcodeError("");
    setPostcodePredictions(null);
    try {
      const resp = await predictPostcode(result.model_id, predictPostcodeVal, predictionDate, postcodeLimit);
      setPostcodePredictions(resp.predictions);
    } catch (e: any) {
      setPostcodeError(e?.response?.data?.detail || "Postcode prediction failed");
    } finally {
      setPredictingPostcode(false);
    }
  }, [result, predictPostcodeVal, predictionDate, postcodeLimit]);

  if (metaError) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8">
        <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
          {metaError}
        </div>
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="flex items-center justify-center py-20 text-gray-500">
        Loading features...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900 dark:text-gray-100">
        Property Price Model
      </h1>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        {/* Sidebar */}
        <div className="space-y-4">
          {/* Data summary */}
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {meta.total_properties_with_sales.toLocaleString()} properties with sales data
            </p>
          </div>

          {/* Target */}
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Target</h3>
            {meta.targets.map((t) => (
              <label key={t.name} className="flex items-center gap-2 py-1 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="radio"
                  name="target"
                  value={t.name}
                  checked={target === t.name}
                  onChange={() => setTarget(t.name)}
                  className="accent-blue-600"
                />
                {t.label}
              </label>
            ))}
          </div>

          {/* Model type */}
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">Model</h3>
            {[
              { value: "lightgbm", label: "LightGBM" },
              { value: "xgboost", label: "XGBoost" },
            ].map((m) => (
              <label key={m.value} className="flex items-center gap-2 py-1 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="radio"
                  name="model"
                  value={m.value}
                  checked={modelType === m.value}
                  onChange={() => setModelType(m.value)}
                  className="accent-blue-600"
                />
                {m.label}
              </label>
            ))}
          </div>

          {/* Split strategy */}
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h3 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">
              Train/Test Split
            </h3>
            <div className="mb-2 flex gap-2">
              <button
                onClick={() => setSplitStrategy("random")}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                  splitStrategy === "random"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-400"
                }`}
              >
                Random
              </button>
              <button
                onClick={() => setSplitStrategy("temporal")}
                className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                  splitStrategy === "temporal"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-400"
                }`}
              >
                Temporal
              </button>
            </div>
            {splitStrategy === "random" ? (
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400">
                  Test ratio: {Math.round(testRatio * 100)}%
                </label>
                <input
                  type="range"
                  min={0.1}
                  max={0.5}
                  step={0.05}
                  value={testRatio}
                  onChange={(e) => setTestRatio(Number(e.target.value))}
                  className="mt-1 w-full accent-blue-600"
                />
              </div>
            ) : (
              <div>
                <label className="text-xs text-gray-500 dark:text-gray-400">Cutoff date</label>
                <input
                  type="date"
                  value={cutoffDate}
                  onChange={(e) => setCutoffDate(e.target.value)}
                  className="mt-1 block w-full rounded border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
                />
              </div>
            )}
          </div>

          {/* Feature selection */}
          <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                Features ({selectedFeatures.size})
              </h3>
              <div className="flex gap-2">
                <button onClick={selectAll} className="text-xs text-blue-600 hover:underline dark:text-blue-400">
                  All
                </button>
                <button onClick={deselectAll} className="text-xs text-blue-600 hover:underline dark:text-blue-400">
                  None
                </button>
              </div>
            </div>
            <div className="max-h-64 space-y-3 overflow-y-auto pr-1">
              {Object.entries(grouped).map(([category, features]) => (
                <div key={category}>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wider text-gray-400 dark:text-gray-500">
                    {category}
                  </p>
                  {features.map((f) => (
                    <label
                      key={f.name}
                      className="flex items-center gap-2 py-0.5 text-xs text-gray-700 dark:text-gray-300"
                    >
                      <input
                        type="checkbox"
                        checked={selectedFeatures.has(f.name)}
                        onChange={() => toggleFeature(f.name)}
                        className="accent-blue-600"
                      />
                      {f.label}
                    </label>
                  ))}
                </div>
              ))}
            </div>
          </div>

          {/* Train button */}
          <button
            onClick={handleTrain}
            disabled={training || selectedFeatures.size === 0}
            className="w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {training ? "Training..." : "Train Model"}
          </button>

          {trainError && (
            <div className="rounded border border-red-300 bg-red-50 p-3 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-400">
              {trainError}
            </div>
          )}
        </div>

        {/* Results */}
        <div className="space-y-6">
          {!result && !training && (
            <div className="flex items-center justify-center rounded-lg border border-dashed border-gray-300 bg-white py-20 text-gray-400 dark:border-gray-700 dark:bg-gray-800">
              Configure features and train a model to see results
            </div>
          )}

          {training && (
            <div className="flex items-center justify-center py-20 text-gray-500">
              <svg className="mr-3 h-5 w-5 animate-spin" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Training model...
            </div>
          )}

          {result && (
            <>
              {/* Metrics */}
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard label="R²" value={result.metrics.r_squared.toFixed(4)} />
                <StatCard label="RMSE" value={`£${result.metrics.rmse.toLocaleString()}`} />
                <StatCard label="MAE" value={`£${result.metrics.mae.toLocaleString()}`} />
                <StatCard label="MAPE" value={`${result.metrics.mape.toFixed(1)}%`} />
              </div>

              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                <StatCard label="Train Size" value={result.train_size.toLocaleString()} />
                <StatCard label="Test Size" value={result.test_size.toLocaleString()} />
                <StatCard label="Model" value={modelType === "lightgbm" ? "LightGBM" : "XGBoost"} />
                <StatCard label="Model ID" value={result.model_id} />
              </div>

              {/* Feature importance chart */}
              <FeatureImportanceChart data={result.feature_importances.slice(0, 20)} colors={colors} />

              {/* Predicted vs Actual scatter */}
              <PredActualScatter predictions={result.predictions} theme={theme} r2={result.metrics.r_squared} />

              {/* Residual histogram */}
              <ResidualHistogram predictions={result.predictions} theme={theme} />

              {/* Worst predictions table */}
              <WorstPredictions predictions={result.predictions} />

              {/* Prediction date */}
              <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
                <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
                  Prediction Date
                </h3>
                <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
                  The model uses this date for sale_year, sale_month, and sale_quarter features.
                </p>
                <input
                  type="date"
                  value={predictionDate}
                  onChange={(e) => setPredictionDate(e.target.value)}
                  className="block w-full rounded border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
                />
              </div>

              {/* Single prediction */}
              <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
                <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
                  Predict Single Property
                </h3>
                <div className="flex items-end gap-3">
                  <div className="flex-1">
                    <label className="text-xs text-gray-500 dark:text-gray-400">Property ID</label>
                    <input
                      type="number"
                      value={predictId}
                      onChange={(e) => setPredictId(e.target.value)}
                      placeholder="e.g. 42"
                      className="mt-1 block w-full rounded border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
                    />
                  </div>
                  <button
                    onClick={handlePredict}
                    disabled={predicting || !predictId}
                    className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50"
                  >
                    {predicting ? "..." : "Predict"}
                  </button>
                </div>
                {predictError && (
                  <p className="mt-2 text-xs text-red-600 dark:text-red-400">{predictError}</p>
                )}
                {prediction && (
                  <div className="mt-3 rounded border border-green-200 bg-green-50 p-3 dark:border-green-800 dark:bg-green-900/30">
                    <p className="text-sm text-green-800 dark:text-green-300">
                      <span className="font-medium">{prediction.address}</span>
                      {" — Predicted: "}
                      <span className="font-bold">£{prediction.predicted_value.toLocaleString()}</span>
                    </p>
                  </div>
                )}
              </div>

              {/* Postcode prediction */}
              <PostcodePredictionSection
                postcode={predictPostcodeVal}
                setPostcode={setPredictPostcodeVal}
                limit={postcodeLimit}
                setLimit={setPostcodeLimit}
                onPredict={handlePredictPostcode}
                predicting={predictingPostcode}
                predictions={postcodePredictions}
                error={postcodeError}
                target={target}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

function FeatureImportanceChart({
  data,
  colors,
}: {
  data: FeatureImportance[];
  colors: ReturnType<typeof getChartColors>;
}) {
  if (!data.length) return null;
  const reversed = [...data].reverse();

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Feature Importance (Top {data.length})
      </h3>
      <ResponsiveContainer width="100%" height={Math.max(250, reversed.length * 28)}>
        <BarChart data={reversed} layout="vertical" margin={{ left: 120, right: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.grid} horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: colors.axis }}
            stroke={colors.grid}
            tickFormatter={(v: number) => `${v}%`}
          />
          <YAxis
            dataKey="feature"
            type="category"
            tick={{ fontSize: 11, fill: colors.axis }}
            stroke={colors.grid}
            width={110}
          />
          <Tooltip
            formatter={(v: number) => `${v.toFixed(1)}%`}
            contentStyle={{
              backgroundColor: colors.tooltipBg,
              borderColor: colors.tooltipBorder,
              color: colors.text,
            }}
          />
          <Bar dataKey="importance" fill="#2563eb" radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PredActualScatter({
  predictions,
  theme,
  r2,
}: {
  predictions: PredictionPoint[];
  theme: ReturnType<typeof usePlotlyTheme>;
  r2: number;
}) {
  if (!predictions.length) return null;

  const actuals = predictions.map((p) => p.actual);
  const predicted = predictions.map((p) => p.predicted);
  const texts = predictions.map((p) => p.address);
  const minVal = Math.min(...actuals, ...predicted);
  const maxVal = Math.max(...actuals, ...predicted);

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Predicted vs Actual
      </h3>
      <Plot
        data={[
          {
            type: "scatter",
            mode: "markers",
            x: actuals,
            y: predicted,
            text: texts,
            marker: { size: 6, opacity: 0.6, color: "#2563eb" },
            hovertemplate:
              "%{text}<br>Actual: £%{x:,.0f}<br>Predicted: £%{y:,.0f}<extra></extra>",
          },
          {
            type: "scatter",
            mode: "lines",
            x: [minVal, maxVal],
            y: [minVal, maxVal],
            line: { color: "#ef4444", width: 2, dash: "dash" },
            hoverinfo: "skip",
            showlegend: false,
          },
        ]}
        layout={{
          paper_bgcolor: "transparent",
          plot_bgcolor: theme.bg,
          font: { color: theme.text, size: 11 },
          xaxis: {
            gridcolor: theme.grid,
            title: { text: "Actual (£)" },
            tickprefix: "£",
            tickformat: ",.0f",
          },
          yaxis: {
            gridcolor: theme.grid,
            title: { text: "Predicted (£)" },
            tickprefix: "£",
            tickformat: ",.0f",
          },
          margin: { t: 10, r: 20, b: 50, l: 80 },
          annotations: [
            {
              x: 0.02,
              y: 0.98,
              xref: "paper",
              yref: "paper",
              text: `R² = ${r2.toFixed(4)}`,
              showarrow: false,
              font: { size: 13, color: theme.text },
            },
          ],
          showlegend: false,
        }}
        config={PLOTLY_CONFIG}
        style={{ width: "100%", height: 400 }}
      />
    </div>
  );
}

function ResidualHistogram({
  predictions,
  theme,
}: {
  predictions: PredictionPoint[];
  theme: ReturnType<typeof usePlotlyTheme>;
}) {
  if (!predictions.length) return null;
  const residuals = predictions.map((p) => p.residual);

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Residual Distribution
      </h3>
      <Plot
        data={[
          {
            type: "histogram",
            x: residuals,
            marker: { color: "#2563eb", opacity: 0.7 },
            hovertemplate: "Range: £%{x:,.0f}<br>Count: %{y}<extra></extra>",
          },
        ]}
        layout={{
          paper_bgcolor: "transparent",
          plot_bgcolor: theme.bg,
          font: { color: theme.text, size: 11 },
          xaxis: {
            gridcolor: theme.grid,
            title: { text: "Prediction Error (£)" },
            tickprefix: "£",
            tickformat: ",.0f",
          },
          yaxis: { gridcolor: theme.grid, title: { text: "Count" } },
          margin: { t: 10, r: 20, b: 50, l: 60 },
          bargap: 0.05,
          showlegend: false,
        }}
        config={PLOTLY_CONFIG}
        style={{ width: "100%", height: 300 }}
      />
    </div>
  );
}

function WorstPredictions({ predictions }: { predictions: PredictionPoint[] }) {
  if (!predictions.length) return null;

  const worst = [...predictions]
    .sort((a, b) => Math.abs(b.residual) - Math.abs(a.residual))
    .slice(0, 10);

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Worst Predictions (Top 10)
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b dark:border-gray-700">
              <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">Address</th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Actual</th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Predicted</th>
              <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Error</th>
            </tr>
          </thead>
          <tbody>
            {worst.map((p) => (
              <tr key={p.property_id} className="border-b dark:border-gray-700/50">
                <td className="py-1.5 text-gray-700 dark:text-gray-300">
                  <a
                    href={`/property/${p.property_id}`}
                    className="hover:text-blue-600 hover:underline dark:hover:text-blue-400"
                  >
                    {p.address}
                  </a>
                </td>
                <td className="py-1.5 text-right text-gray-700 dark:text-gray-300">
                  £{p.actual.toLocaleString()}
                </td>
                <td className="py-1.5 text-right text-gray-700 dark:text-gray-300">
                  £{Math.round(p.predicted).toLocaleString()}
                </td>
                <td
                  className={`py-1.5 text-right font-medium ${
                    p.residual > 0
                      ? "text-red-600 dark:text-red-400"
                      : "text-green-600 dark:text-green-400"
                  }`}
                >
                  {p.residual > 0 ? "+" : ""}£{Math.round(p.residual).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PostcodePredictionSection({
  postcode,
  setPostcode,
  limit,
  setLimit,
  onPredict,
  predicting,
  predictions,
  error,
  target,
}: {
  postcode: string;
  setPostcode: (v: string) => void;
  limit: number;
  setLimit: (v: number) => void;
  onPredict: () => void;
  predicting: boolean;
  predictions: PostcodePredictionItem[] | null;
  error: string;
  target: string;
}) {
  const fmt = (v: number | null) =>
    v != null ? `£${Math.round(v).toLocaleString()}` : "—";
  const pctFmt = (v: number | null) =>
    v != null ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "—";
  const isPrice = target === "price_numeric" || target === "price_per_sqft";

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm dark:border-gray-700 dark:bg-gray-800">
      <h3 className="mb-3 text-lg font-bold text-gray-800 dark:text-gray-200">
        Predict by Postcode
      </h3>
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="text-xs text-gray-500 dark:text-gray-400">Postcode</label>
          <input
            type="text"
            value={postcode}
            onChange={(e) => setPostcode(e.target.value.toUpperCase())}
            onKeyDown={(e) => e.key === "Enter" && onPredict()}
            placeholder="e.g. SW18 1AP"
            className="mt-1 block w-full rounded border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 dark:text-gray-400">Max</label>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="mt-1 block rounded border border-gray-300 bg-white px-2 py-1.5 text-sm shadow-sm dark:border-gray-600 dark:bg-gray-700 dark:text-gray-200"
          >
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={200}>200</option>
          </select>
        </div>
        <button
          onClick={onPredict}
          disabled={predicting || !postcode.trim()}
          className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50"
        >
          {predicting ? "Predicting..." : "Predict Postcode"}
        </button>
      </div>
      {error && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p>
      )}
      {predictions && predictions.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-sm text-gray-500 dark:text-gray-400">
            {predictions.length} properties found
          </p>
          <div className="max-h-[500px] overflow-auto">
            <table className="w-full text-left text-sm">
              <thead className="sticky top-0 bg-white dark:bg-gray-800">
                <tr className="border-b dark:border-gray-700">
                  <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">Address</th>
                  <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Predicted</th>
                  {isPrice && (
                    <>
                      <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Last Sale</th>
                      <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Diff</th>
                      <th className="pb-2 text-right font-medium text-gray-500 dark:text-gray-400">Diff %</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {predictions.map((p) => (
                  <tr key={p.property_id} className="border-b dark:border-gray-700/50">
                    <td className="py-1.5 text-gray-700 dark:text-gray-300">
                      <a
                        href={`/property/${p.property_id}`}
                        className="hover:text-blue-600 hover:underline dark:hover:text-blue-400"
                      >
                        {p.address}
                      </a>
                    </td>
                    <td className="py-1.5 text-right font-medium text-gray-700 dark:text-gray-300">
                      {fmt(p.predicted_value)}
                    </td>
                    {isPrice && (
                      <>
                        <td className="py-1.5 text-right text-gray-700 dark:text-gray-300">
                          {fmt(p.last_sale_price)}
                        </td>
                        <td
                          className={`py-1.5 text-right font-medium ${
                            p.difference != null && p.difference > 0
                              ? "text-green-600 dark:text-green-400"
                              : p.difference != null && p.difference < 0
                                ? "text-red-600 dark:text-red-400"
                                : "text-gray-500"
                          }`}
                        >
                          {fmt(p.difference)}
                        </td>
                        <td
                          className={`py-1.5 text-right font-medium ${
                            p.difference_pct != null && p.difference_pct > 0
                              ? "text-green-600 dark:text-green-400"
                              : p.difference_pct != null && p.difference_pct < 0
                                ? "text-red-600 dark:text-red-400"
                                : "text-gray-500"
                          }`}
                        >
                          {pctFmt(p.difference_pct)}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {predictions && predictions.length === 0 && (
        <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
          No properties found for this postcode.
        </p>
      )}
    </div>
  );
}
