"use client";

import { ColorType, createChart, HistogramSeries, LineSeries, type UTCTimestamp } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

type Bar = { time: string; value: number; volume: number; simulated: boolean };

export function PriceChart({ symbol }: { symbol: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("Loading chart history");
  const [simulated, setSimulated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let chart: ReturnType<typeof createChart> | undefined;
    let observer: ResizeObserver | undefined;
    api<{ items: Bar[]; status: string; simulated: boolean }>(`/api/stocks/${symbol}/history`)
      .then((data) => {
        if (cancelled || !host.current) return;
        setSimulated(data.simulated);
        if (!data.items.length) { setStatus("Chart history unavailable"); return; }
        chart = createChart(host.current, {
          width: host.current.clientWidth,
          height: 260,
          layout: { background: { type: ColorType.Solid, color: "#111713" }, textColor: "#9ba9a0", fontFamily: "IBM Plex Mono, monospace" },
          grid: { vertLines: { color: "#202a24" }, horzLines: { color: "#202a24" } },
          rightPriceScale: { borderColor: "#354139" },
          timeScale: { borderColor: "#354139", timeVisible: true },
          crosshair: { vertLine: { color: "#94f1b2" }, horzLine: { color: "#94f1b2" } },
        });
        const line = chart.addSeries(LineSeries, {
          color: "#8df0ae", lineWidth: 2, crosshairMarkerRadius: 3,
        });
        line.setData(data.items.map((bar) => ({
          time: Math.floor(new Date(bar.time).getTime() / 1000) as UTCTimestamp,
          value: bar.value,
        })));
        const volume = chart.addSeries(HistogramSeries, { priceScaleId: "volume", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
        volume.setData(data.items.map((bar) => ({ time: Math.floor(new Date(bar.time).getTime() / 1000) as UTCTimestamp, value: bar.volume, color: "#487e61" })));
        chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });
        chart.timeScale().fitContent();
        setStatus(data.status === "available" ? `${data.items.length} observations` : "Chart history unavailable");
        observer = new ResizeObserver(([entry]) => chart?.applyOptions({ width: entry.contentRect.width }));
        observer.observe(host.current);
      })
      .catch((error: Error) => { if (!cancelled) setStatus(error.message); });
    return () => { cancelled = true; observer?.disconnect(); chart?.remove(); };
  }, [symbol]);

  return <div className="chart-frame"><div ref={host} className="chart-canvas" aria-label={`${symbol} price and volume chart`} /><div className="chart-caption">{status}{simulated && <span className="tag tag-demo">SIMULATED FIXTURE</span>}</div></div>;
}