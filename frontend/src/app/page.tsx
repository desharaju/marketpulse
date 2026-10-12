"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, Bell, CalendarClock, ChevronDown,
  ChevronLeft, ChevronRight, CircleHelp, Download, ExternalLink, Eye, Filter, Gauge,
  LayoutDashboard, Menu, Moon, Newspaper, Plus, RefreshCw, Search, Send,
  Settings2, SlidersHorizontal, Sun, TrendingUp, Volume2, X,
} from "lucide-react";
import { PriceChart } from "@/components/PriceChart";
import { api, API_URL } from "@/lib/api";
import { formatCompact, formatMoney, formatPercent, formatTimestamp } from "@/lib/format";

type Stock = {
  symbol: string; company: string; price: number | null; change: number | null; changePercent: number | null;
  volume: number | null; averageVolume: number | null; relativeVolume: number | null; fullDayRvolEstimate: number | null;
  dollarVolume: number | null; marketCap: number | null; source: string; asOf: string | null; simulated: boolean;
  volumeUnavailableReason?: string | null;
  ranking: { score: number; breakdown: Record<string, number>; signalsAvailable: string[] };
};
type MarketMeta = { mode: string; source: string; asOf: string | null; delayStatus: string; simulated: boolean; limitations: string[]; marketSession: { status: string; timezone: string; isTradingDay: boolean }; freshness: { ageSeconds: number | null } };
type Section = "Overview" | "Live Quotes" | "Trending" | "Unusual Volume" | "Premarket" | "News & Catalysts" | "Watchlists" | "Alerts" | "Email Reports" | "Settings";
type ReportPreview = { report: { reportDate: string; dataAsOf: string | null; mode: string; sections: { title: string; status: string; items: Stock[] }[]; limitations: string[] }; text: string };
type ReportSettings = { recipient: string; additional_recipients: string[]; report_time: string; min_relative_volume: number; min_change_percent: number; min_price: number; min_dollar_volume: number; max_tickers_per_section: number; format: string };
type NewsStory = { headline: string; publisher: string; publishedAt: string | null; url: string; summary?: string | null };

const navItems: { label: Section; icon: typeof Activity }[] = [
  { label: "Overview", icon: LayoutDashboard }, { label: "Live Quotes", icon: Activity },
  { label: "Trending", icon: TrendingUp }, { label: "Unusual Volume", icon: Volume2 },
  { label: "Premarket", icon: Sun }, { label: "News & Catalysts", icon: Newspaper },
  { label: "Watchlists", icon: Eye }, { label: "Alerts", icon: Bell },
  { label: "Email Reports", icon: CalendarClock }, { label: "Settings", icon: Settings2 },
];

export default function Dashboard() {
  const [section, setSection] = useState<Section>("Overview");
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [meta, setMeta] = useState<MarketMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [minPrice, setMinPrice] = useState("");
  const [sortBy, setSortBy] = useState("volume");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [theme, setTheme] = useState("dark");
  const [adminKey, setAdminKey] = useState("");
  const [now, setNow] = useState(new Date());
  const [news, setNews] = useState<NewsStory[]>([]);
  const [tickerNews, setTickerNews] = useState<{ symbol: string; items: NewsStory[] } | null>(null);
  const [watchlists, setWatchlists] = useState<{ id: number; name: string; symbols: string[] }[]>([]);
  const [alerts, setAlerts] = useState<{ rules: { id: number; symbol: string; metric: string; threshold: number; direction: string }[]; events: { id: number; symbol: string; message: string; triggeredAt: string }[] }>({ rules: [], events: [] });
  const [reports, setReports] = useState<{ id: number; recipient: string; reportDate: string; status: string; error: string | null }[]>([]);
  const [reportSettings, setReportSettings] = useState<ReportSettings>({ recipient: "", additional_recipients: [], report_time: "08:00", min_relative_volume: 2, min_change_percent: 0, min_price: 0, min_dollar_volume: 0, max_tickers_per_section: 10, format: "html" });
  const [preview, setPreview] = useState<ReportPreview | null>(null);
  const [notice, setNotice] = useState("");
  const [mobileNav, setMobileNav] = useState(false);

  const loadDashboard = useCallback(async (force = false) => {
    setLoading(true);
    setError("");
    try {
      const overview = await api<MarketMeta>(`/api/market/overview?refresh=${force}`);
      setMeta(overview);
      const params = new URLSearchParams({ sort_by: sortBy, page: String(page), page_size: "20" });
      if (search) params.set("search", search);
      if (minPrice) params.set("min_price", minPrice);
      params.set("refresh", String(force));
      const endpoint = section === "Trending" ? `/api/stocks/trending?refresh=${force}` : section === "Unusual Volume" ? `/api/stocks/unusual-volume?refresh=${force}` : section === "Premarket" ? `/api/stocks/premarket?refresh=${force}` : `/api/stocks/most-active?${params}`;
      const result = await api<{ items: Stock[]; errors?: { message: string }[] }>(endpoint);
      setStocks(result.items || []);
      if (result.errors?.length && !result.items?.length) setError(result.errors[0].message);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Market data unavailable");
      setStocks([]);
    } finally { setLoading(false); }
  }, [minPrice, page, search, section, sortBy]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => { void loadDashboard(); }, 0);
    const timer = window.setInterval(() => { if (document.visibilityState === "visible") void loadDashboard(); }, 60_000);
    return () => { window.clearTimeout(initialRefresh); window.clearInterval(timer); };
  }, [loadDashboard]);

  useEffect(() => {
    if (section === "News & Catalysts") void api<{ items: typeof news }>("/api/news").then((data) => setNews(data.items)).catch(() => setNews([]));
    if (section === "Watchlists") void api<typeof watchlists>("/api/watchlists").then(setWatchlists).catch(() => setWatchlists([]));
    if (section === "Alerts") void api<typeof alerts>("/api/alerts").then(setAlerts).catch(() => setAlerts({ rules: [], events: [] }));
    if (section === "Email Reports") {
      void api<typeof reports>("/api/reports").then(setReports).catch(() => setReports([]));
      void api<ReportSettings>("/api/settings/reports").then(setReportSettings).catch(() => undefined);
    }
    if (section === "Settings") void api<ReportSettings>("/api/settings/reports").then(setReportSettings).catch(() => undefined);
  }, [adminKey, section]);

  useEffect(() => {
    if (selected) void api<{ symbol: string; items: NewsStory[] }>(`/api/stocks/${selected}/news`).then(setTickerNews).catch(() => setTickerNews(null));
  }, [selected]);

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const visibleStocks = stocks;
  const changeUp = stocks.filter((stock) => (stock.changePercent || 0) > 0).length;
  const changeDown = stocks.filter((stock) => (stock.changePercent || 0) < 0).length;
  const marketDate = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "long", month: "long", day: "numeric" }).format(now).toUpperCase();

  async function refresh() { await loadDashboard(true); }
  function exportCsv() {
    const headers = ["symbol", "company", "price", "change", "changePercent", "volume", "averageVolume", "relativeVolume", "dollarVolume", "source", "asOf"];
    const rows = visibleStocks.map((stock) => headers.map((key) => JSON.stringify((stock as unknown as Record<string, unknown>)[key] ?? "")).join(","));
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([[headers.join(","), ...rows].join("\n")], { type: "text/csv" }));
    link.download = `marketpulse-${section.toLowerCase().replaceAll(" ", "-")}.csv`;
    link.click(); URL.revokeObjectURL(link.href);
  }

  async function makePreview() {
    try { setPreview(await api<ReportPreview>("/api/reports/preview", { method: "POST", body: JSON.stringify({}) })); }
    catch (reason) { setNotice(reason instanceof Error ? reason.message : "Preview unavailable"); }
  }

  async function sendReport() {
    try {
      const result = await api<{ status?: string; results?: { status: string }[] }>("/api/reports/generate", { method: "POST", body: JSON.stringify({ send: true }) });
      setNotice(result.status ? `Report ${result.status}` : `Reports ${result.results?.map((item) => item.status).join(", ")}`);
      setReports(await api<typeof reports>("/api/reports"));
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Report send failed"); }
  }

  async function sendTestEmail() {
    if (!reportSettings.recipient) { setNotice("Set a primary recipient before sending a test email"); return; }
    try {
      await api("/api/reports/send-test", { method: "POST", body: JSON.stringify({ recipient: reportSettings.recipient }) });
      setNotice(`Test email sent to ${reportSettings.recipient}`);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Test email failed"); }
  }

  async function saveReportSettings() {
    try {
      await api("/api/settings/reports", { method: "POST", body: JSON.stringify(reportSettings) });
      setNotice("Report settings saved");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Settings were not saved"); }
  }

  async function saveWatchlist(form: FormData) {
    const name = String(form.get("name") || "My watchlist");
    try {
      await api("/api/watchlists", { method: "POST", body: JSON.stringify({ name }) });
      setWatchlists(await api("/api/watchlists"));
      setNotice("Watchlist created");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Could not create watchlist"); }
  }

  async function addWatchlistSymbol(watchlistId: number, form: FormData) {
    const symbol = String(form.get("symbol") || "").toUpperCase();
    try {
      await api(`/api/watchlists/${watchlistId}/items`, { method: "POST", body: JSON.stringify({ symbol }) });
      setWatchlists(await api<typeof watchlists>("/api/watchlists"));
      setNotice(`${symbol} added to watchlist`);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Could not add ticker"); }
  }

  async function removeWatchlistSymbol(watchlistId: number, symbol: string) {
    try {
      await api(`/api/watchlists/${watchlistId}/items/${symbol}`, { method: "DELETE" });
      setWatchlists(await api<typeof watchlists>("/api/watchlists"));
      setNotice(`${symbol} removed from watchlist`);
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Could not remove ticker"); }
  }

  async function saveAlert(form: FormData) {
    const payload = { symbol: String(form.get("symbol") || "").toUpperCase(), metric: String(form.get("metric") || "relativeVolume"), threshold: Number(form.get("threshold") || 2), direction: String(form.get("direction") || "above") };
    try {
      await api("/api/alerts", { method: "POST", body: JSON.stringify(payload) });
      setAlerts(await api("/api/alerts")); setNotice("Alert rule created");
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : "Could not create alert"); }
  }

  const pageTitle = section === "Overview" ? "Market overview" : section;
  const session = meta?.marketSession?.status || "unavailable";
  const listMode = ["Overview", "Live Quotes", "Trending", "Unusual Volume", "Premarket"].includes(section);

  return (
    <main className="app-shell">
      <aside className={`sidebar ${mobileNav ? "sidebar-open" : ""}`}>
        <div className="brand"><div className="brand-mark"><Activity size={20} /></div><div><strong>marketpulse</strong><small>MARKET INTELLIGENCE</small></div><button className="icon-button mobile-close" title="Close navigation" onClick={() => setMobileNav(false)}><X size={17} /></button></div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="nav-list" aria-label="Main navigation">
          {navItems.map(({ label, icon: Icon }) => <button key={label} className={`nav-link ${section === label ? "active" : ""}`} onClick={() => { setSection(label); setMobileNav(false); setPage(1); }}><Icon size={16} strokeWidth={1.8} /><span>{label}</span>{label === "Alerts" && alerts.events.length > 0 && <b className="nav-count">{alerts.events.length}</b>}</button>)}
        </nav>
        <div className="sidebar-bottom"><div className="api-indicator"><span className={meta?.mode === "provider" ? "status-dot live" : "status-dot demo"} /><div><strong>{meta?.mode === "provider" ? meta.source : "Demo feed"}</strong><small>{meta?.mode === "provider" ? "PLAN-DEPENDENT DATA" : "ILLUSTRATIVE FIXTURES"}</small></div></div><div className="sidebar-foot">MARKETPULSE · RESEARCH ONLY</div></div>
      </aside>
      {mobileNav && <button aria-label="Close menu overlay" className="nav-scrim" onClick={() => setMobileNav(false)} />}
      <section className="main-area">
        <header className="topbar"><button className="icon-button menu-toggle" title="Open navigation" onClick={() => setMobileNav(true)}><Menu size={18} /></button><div className="breadcrumb">SCANNER <span>/</span> {section.toUpperCase()}</div><div className="topbar-tools"><div className="market-clock"><span>{now.toLocaleTimeString("en-US", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", timeZoneName: "short" })}</span><small>NEW YORK</small></div><span className={`session-pill session-${session}`}>{session.replace("-", " ")}</span><button className="icon-button" title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}</button><button className="icon-button" title="Refresh scanner data" onClick={refresh}><RefreshCw size={16} className={loading ? "spin" : ""} /></button></div></header>
        <div className="content-wrap">
          {meta?.mode === "demo" && <div className="demo-banner"><AlertTriangle size={15} /><span><strong>DEMO DATA</strong> Fixed illustrative fixtures only. No current market observations are connected.</span><a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">Configure provider <ExternalLink size={12} /></a></div>}
          {meta?.mode === "provider" && <div className="freshness-line"><span className="status-dot live" /> {meta.source} · {meta.delayStatus} · as of {formatTimestamp(meta.asOf)} · {meta.freshness.ageSeconds == null ? "freshness unknown" : `${meta.freshness.ageSeconds}s old`}</div>}
          {meta?.mode === "provider" && meta.limitations.some((limitation) => limitation.includes("intraday candles are unavailable")) && <div className="notice" role="status"><AlertTriangle size={15} /><span>Finnhub quotes are available. Candle access is unavailable for this account, so volume-derived fields cannot be shown.</span></div>}
          <div className="page-heading"><div><div className="eyebrow">{marketDate} <span className="eyebrow-divider">/</span> US EQUITIES</div><h1>{pageTitle}</h1></div><div className="heading-actions">{listMode && <button className="button button-quiet" onClick={exportCsv}><Download size={15} /> Export CSV</button>}{section === "Email Reports" && <button className="button button-primary" onClick={makePreview}><Eye size={15} /> Preview report</button>}</div></div>

          {notice && <div className="notice" role="status">{notice}<button className="icon-button" title="Dismiss message" onClick={() => setNotice("")}><X size={14} /></button></div>}
          {section === "Overview" && <><div className="index-strip">{["S&P 500", "NASDAQ", "DOW JONES", "RUSSELL 2000"].map((name) => <div className="index-cell" key={name}><span>{name}</span><strong>--</strong><small>INDEX FEED UNAVAILABLE</small></div>)}</div><div className="market-summary"><div><span className="metric-label">SESSION</span><strong className="session-title">{session.replace("-", " ")}</strong><small>{meta?.marketSession?.timezone || "America/New_York"}</small></div><div><span className="metric-label">SCANNER UNIVERSE</span><strong>{meta ? stocks.length : "--"} <small>symbols loaded</small></strong><small>Configured symbols only</small></div><div><span className="metric-label">ADVANCERS / DECLINERS</span><strong><span className="positive-text">{changeUp}</span><span className="metric-slash"> / </span><span className="negative-text">{changeDown}</span></strong><small>Current scanner universe</small></div><div><span className="metric-label">LAST SUCCESSFUL UPDATE</span><strong className="metric-time">{formatTimestamp(meta?.asOf)}</strong><small>{meta?.delayStatus || "Awaiting provider"}</small></div></div></>}

          {listMode && <div className="data-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Gauge size={16} /></div><div><h2>{section === "Overview" ? "Live quotes" : section === "Premarket" ? "Premarket scanner" : section}</h2><p>{section === "Unusual Volume" ? "Same-time volume vs prior sessions · elevated activity is not a directional signal" : section === "Trending" ? "Transparent score · absent signals are excluded" : "Latest available provider observations"}</p></div></div><div className="filters"><label className="search-control"><Search size={14} /><input aria-label="Search ticker or company" placeholder="Symbol or company" value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void loadDashboard(true)} /><kbd>↵</kbd></label><label className="price-filter"><span>MIN PRICE</span><input aria-label="Minimum price" type="number" min="0" placeholder="Any" value={minPrice} onChange={(event) => setMinPrice(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void loadDashboard(true)} /></label><button className="icon-button filter-button" title="Apply scanner filters" onClick={() => void loadDashboard(true)}><Filter size={15} /></button></div></div>
            <div className="table-scroll"><table className="stock-table"><thead><tr><th className="th-symbol">SYMBOL</th><th>PRICE</th><th><button className="sort-button" onClick={() => setSortBy("change")}>PRICE CHG <ChevronDown size={12} /></button></th><th><button className="sort-button" onClick={() => setSortBy("changePercent")}>CHANGE % <ChevronDown size={12} /></button></th><th><button className="sort-button" onClick={() => setSortBy("volume")}>VOLUME <ChevronDown size={12} /></button></th><th>AVG VOL</th><th>REL VOL</th><th><button className="sort-button" onClick={() => setSortBy("dollarVolume")}>DOLLAR VOL <ChevronDown size={12} /></button></th><th>RANK SCORE</th><th>SOURCE / TIME</th></tr></thead><tbody>
              {loading && Array.from({ length: 6 }, (_, index) => <tr className="skeleton-row" key={index}><td colSpan={10}><span /></td></tr>)}
              {!loading && visibleStocks.map((stock) => <tr key={stock.symbol} className="stock-row" onClick={() => setSelected(stock.symbol)} tabIndex={0} onKeyDown={(event) => event.key === "Enter" && setSelected(stock.symbol)}><td><div className="ticker-cell"><strong>{stock.symbol}</strong><small>{stock.company}</small></div></td><td className="mono">{formatMoney(stock.price)}</td><td className={`mono ${(stock.change || 0) >= 0 ? "positive-text" : "negative-text"}`}>{formatMoney(stock.change)}</td><td><span className={`change-value ${(stock.changePercent || 0) >= 0 ? "positive-text" : "negative-text"}`}>{(stock.changePercent || 0) >= 0 ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{formatPercent(stock.changePercent)}</span></td><td className="mono">{formatCompact(stock.volume)}</td><td className="mono muted-text">{formatCompact(stock.averageVolume)}</td><td>{stock.relativeVolume == null ? <span className="tag tag-muted">N/A</span> : <span className={`rvol-tag ${stock.relativeVolume >= 2 ? "rvol-hot" : ""}`}>{stock.relativeVolume.toFixed(2)}x</span>}</td><td className="mono">{formatCompact(stock.dollarVolume)}</td><td><span className="score-cell" title={`Score ${stock.ranking?.score ?? "--"}. Breakdown: ${JSON.stringify(stock.ranking?.breakdown || {})}`}><i style={{ width: `${stock.ranking?.score || 0}%` }} /><b>{stock.ranking?.score?.toFixed(0) ?? "--"}</b></span></td><td className="source-cell"><span>{stock.source}</span><small>{stock.volumeUnavailableReason || formatTimestamp(stock.asOf)}</small></td></tr>)}
              {!loading && !visibleStocks.length && <tr><td colSpan={10}><div className="empty-state">{error ? <><AlertTriangle size={20} /><strong>Market data unavailable</strong><p>{error}</p></> : section === "Premarket" ? <><Sun size={20} /><strong>Premarket feed unavailable</strong><p>The configured provider does not supply premarket trades. No regular-session data is substituted.</p></> : <><Search size={20} /><strong>No matching symbols</strong><p>Adjust the search or price filter.</p></>}</div></td></tr>}
              </tbody></table></div><div className="table-footer"><span>{visibleStocks.length} results <span className="footer-dot">·</span> {meta?.mode === "demo" ? "Illustrative sample" : "First 30 Finnhub directory symbols"}</span><div className="pager"><button className="icon-button" aria-label="Previous page" onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}><ChevronLeft size={15} /></button><span>{page}</span><button className="icon-button" aria-label="Next page" onClick={() => setPage(page + 1)} disabled={visibleStocks.length < 20}><ChevronRight size={15} /></button></div></div>
          </div>}

          {section === "News & Catalysts" && <div className="data-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Newspaper size={16} /></div><div><h2>News & Catalysts</h2><p>Original publisher headlines · deduplicated by URL</p></div></div></div>{news.length ? <div className="news-list">{news.map((story) => <a className="news-row" href={story.url} target="_blank" rel="noreferrer" key={story.url}><div><strong>{story.headline}</strong><small>{story.publisher} · {formatTimestamp(story.publishedAt)}</small></div><ExternalLink size={15} /></a>)}</div> : <div className="empty-state"><Newspaper size={20} /><strong>No permitted news feed available</strong><p>News is unavailable in demo mode or no licensed provider headlines matched the scanner universe.</p></div>}</div>}

          {section === "Watchlists" && <div className="workspace-grid"><div className="data-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Eye size={16} /></div><div><h2>Saved watchlists</h2><p>Private to this single-user deployment</p></div></div></div><form action={saveWatchlist} className="inline-form"><input name="name" aria-label="Watchlist name" placeholder="New watchlist name" maxLength={80} required /><button className="button button-primary"><Plus size={15} /> Create watchlist</button></form>{watchlists.map((list) => <div className="watchlist-block" key={list.id}><div className="watchlist-row"><strong>{list.name}</strong><span>{list.symbols.length} symbols</span></div><form action={(form) => addWatchlistSymbol(list.id, form)} className="watchlist-item-form"><input name="symbol" aria-label={`Ticker to add to ${list.name}`} placeholder="Add ticker" maxLength={16} pattern="[A-Za-z][A-Za-z0-9.-]*" required /><button className="icon-button" title={`Add ticker to ${list.name}`}><Plus size={15} /></button></form><div className="watchlist-symbols">{list.symbols.map((symbol) => <span className="watchlist-chip" key={symbol}><button onClick={() => setSelected(symbol)}>{symbol}</button><button className="icon-button" title={`Remove ${symbol}`} onClick={() => void removeWatchlistSymbol(list.id, symbol)}><X size={12} /></button></span>)}</div></div>)}{!watchlists.length && <div className="empty-state compact-empty">Create a watchlist to start tracking symbols.</div>}</div><div className="data-panel side-note"><h3>Watchlist data</h3><p>MarketPulse scans the configured symbol universe. Watchlist-only symbols are saved for organization but do not yet expand the provider scan.</p></div></div>}

          {section === "Alerts" && <div className="workspace-grid"><div className="data-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Bell size={16} /></div><div><h2>Alert rules</h2><p>30-minute cooldown · checked on scanner refresh</p></div></div></div><form action={saveAlert} className="alert-form"><label>SYMBOL<input name="symbol" placeholder="NVDA" required pattern="[A-Za-z][A-Za-z0-9.-]*" /></label><label>METRIC<select name="metric"><option value="relativeVolume">Relative volume</option><option value="changePercent">Change %</option><option value="price">Price</option></select></label><label>CONDITION<select name="direction"><option value="above">Above</option><option value="below">Below</option></select></label><label>THRESHOLD<input name="threshold" type="number" step="0.01" defaultValue="2" required /></label><button className="button button-primary"><Plus size={15} /> Add rule</button></form>{alerts.rules.map((rule) => <div className="watchlist-row" key={rule.id}><strong>{rule.symbol}</strong><span>{rule.metric} {rule.direction} {rule.threshold}</span></div>)}{!alerts.rules.length && <div className="empty-state compact-empty">No alert rules configured.</div>}</div><div className="data-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Activity size={16} /></div><div><h2>Recent alert events</h2><p>Recorded triggers</p></div></div></div>{alerts.events.map((event) => <div className="event-row" key={event.id}><span className="event-dot" /><div><strong>{event.symbol}</strong><p>{event.message}</p><small>{formatTimestamp(event.triggeredAt)}</small></div></div>)}{!alerts.events.length && <div className="empty-state compact-empty">No alert events recorded.</div>}</div></div>}

          {section === "Email Reports" && <div className="reports-layout"><div className="data-panel report-config"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><CalendarClock size={16} /></div><div><h2>Premarket report</h2><p>Scheduled on XNYS trading days · America/New_York</p></div></div></div><label className="field-label">PRIMARY RECIPIENT<input type="email" value={reportSettings.recipient} onChange={(event) => setReportSettings({ ...reportSettings, recipient: event.target.value })} placeholder="research@example.com" /></label><label className="field-label additional-field">ADDITIONAL RECIPIENTS<input type="text" value={reportSettings.additional_recipients.join(", ")} onChange={(event) => setReportSettings({ ...reportSettings, additional_recipients: event.target.value.split(",").map((address) => address.trim()).filter(Boolean) })} placeholder="team@example.com, analyst@example.com" /></label><div className="config-pair"><label className="field-label">DELIVERY TIME<input type="time" value={reportSettings.report_time} onChange={(event) => setReportSettings({ ...reportSettings, report_time: event.target.value })} /></label><label className="field-label">MAX TICKERS / SECTION<input type="number" min="1" max="100" value={reportSettings.max_tickers_per_section} onChange={(event) => setReportSettings({ ...reportSettings, max_tickers_per_section: Number(event.target.value) })} /></label></div><div className="config-pair"><label className="field-label">MIN RELATIVE VOLUME<input type="number" min="1" step="0.1" value={reportSettings.min_relative_volume} onChange={(event) => setReportSettings({ ...reportSettings, min_relative_volume: Number(event.target.value) })} /></label><label className="field-label">MIN PRICE<input type="number" min="0" step="0.01" value={reportSettings.min_price} onChange={(event) => setReportSettings({ ...reportSettings, min_price: Number(event.target.value) })} /></label></div><div className="report-buttons"><button className="button button-quiet" onClick={saveReportSettings}><SlidersHorizontal size={15} /> Save settings</button><button className="button button-quiet" onClick={sendTestEmail}><Send size={15} /> Send test email</button><button className="button button-primary" onClick={sendReport}><Send size={15} /> Generate &amp; send</button></div><p className="form-footnote">SMTP must be configured server-side. Sending is idempotent for each recipient and New York market date.</p></div><div className="data-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Activity size={16} /></div><div><h2>Delivery history</h2><p>Generation and delivery status</p></div></div></div>{reports.map((report) => <div className="report-row" key={report.id}><div><strong>{report.reportDate}</strong><small>{report.recipient}</small></div><span className={`tag tag-${report.status}`}>{report.status}</span>{report.error && <small className="error-text">{report.error}</small>}</div>)}{!reports.length && <div className="empty-state compact-empty">No reports generated.</div>}</div></div>}

          {section === "Settings" && <div className="data-panel settings-panel"><div className="panel-toolbar"><div className="panel-title"><div className="panel-icon"><Settings2 size={16} /></div><div><h2>Report configuration</h2><p>Schedule and scanner thresholds</p></div></div></div><label className="field-label">ADMIN API KEY<input type="password" value={adminKey} onChange={(event) => { const value = event.target.value; setAdminKey(value); if (value) window.sessionStorage.setItem("marketpulse-admin-key", value); else window.sessionStorage.removeItem("marketpulse-admin-key"); }} autoComplete="off" placeholder="Required only when configured on the API" /></label><label className="field-label">RECIPIENT EMAIL<input type="email" value={reportSettings.recipient} onChange={(event) => setReportSettings({ ...reportSettings, recipient: event.target.value })} placeholder="research@example.com" /></label><label className="field-label">ADDITIONAL RECIPIENTS<input type="text" value={reportSettings.additional_recipients.join(", ")} onChange={(event) => setReportSettings({ ...reportSettings, additional_recipients: event.target.value.split(",").map((address) => address.trim()).filter(Boolean) })} placeholder="team@example.com, analyst@example.com" /></label><label className="field-label">NEW YORK DELIVERY TIME<input type="time" value={reportSettings.report_time} onChange={(event) => setReportSettings({ ...reportSettings, report_time: event.target.value })} /></label><label className="field-label">MINIMUM RELATIVE VOLUME<input type="number" min="1" value={reportSettings.min_relative_volume} onChange={(event) => setReportSettings({ ...reportSettings, min_relative_volume: Number(event.target.value) })} /></label><button className="button button-primary" onClick={saveReportSettings}><SlidersHorizontal size={15} /> Save settings</button><div className="limitations-box"><CircleHelp size={16} /><p>Provider credentials remain server-side. Configure `FINNHUB_API_KEY` and SMTP credentials in the deployment environment. Index quotes, premarket trades, licensed news and earnings feeds are not enabled in this release.</p></div></div>}

          {meta?.limitations?.length && <div className="limitations-line"><CircleHelp size={14} /><span>{meta.limitations.join(" ")}</span></div>}
          <footer className="page-footer"><span>MARKETPULSE <span className="footer-dot">·</span> INFORMATIONAL RESEARCH TOOL, NOT INVESTMENT ADVICE</span><span>UPDATE {formatTimestamp(meta?.asOf)}</span></footer>
        </div>
      </section>

      {selected && (
        <div className="drawer-backdrop" onClick={() => setSelected(null)}>
          <aside className="detail-drawer" onClick={(event) => event.stopPropagation()}>
            <div className="drawer-head">
              <div><span className="eyebrow">EQUITY DETAIL</span><h2>{selected}</h2></div>
              <button className="icon-button" title="Close stock detail" onClick={() => setSelected(null)}><X size={18} /></button>
            </div>
            <PriceChart symbol={selected} />
            <div className="drawer-section">
              <div className="drawer-section-title"><h3>Quote facts</h3><span>{meta?.source || "No source"}</span></div>
              {stocks.filter((stock) => stock.symbol === selected).map((stock) => (
                <div className="detail-grid" key={stock.symbol}>
                  <div><small>LAST</small><strong>{formatMoney(stock.price)}</strong></div>
                  <div><small>CHANGE</small><strong className={(stock.changePercent || 0) >= 0 ? "positive-text" : "negative-text"}>{formatPercent(stock.changePercent)}</strong></div>
                  <div><small>SESSION VOLUME</small><strong>{formatCompact(stock.volume)}</strong></div>
                  <div><small>RELATIVE VOLUME</small><strong>{stock.relativeVolume?.toFixed(2) ?? "--"}x</strong></div>
                  <div><small>MARKET CAP</small><strong>{formatCompact(stock.marketCap)}</strong></div>
                  <div><small>DATA AS OF</small><strong>{formatTimestamp(stock.asOf)}</strong></div>
                </div>
              ))}
            </div>
            <div className="drawer-section">
              <div className="drawer-section-title"><h3>News</h3><span>Original source links</span></div>
              {tickerNews?.symbol === selected && tickerNews.items.length ? tickerNews.items.map((story) => <a className="news-row detail-news" href={story.url} target="_blank" rel="noreferrer" key={story.url}><div><strong>{story.headline}</strong><small>{story.publisher} · {formatTimestamp(story.publishedAt)}</small></div><ExternalLink size={14} /></a>) : <p className="form-footnote">No publisher-linked news available for this ticker from the configured provider.</p>}
              <p className="form-footnote">Verified provider facts and calculated indicators are shown separately. No causal price-move claims are inferred.</p>
            </div>
          </aside>
        </div>
      )}

      {preview && <div className="modal-backdrop" onClick={() => setPreview(null)}><section className="report-modal" onClick={(event) => event.stopPropagation()}><div className="modal-head"><div><span className="eyebrow">REPORT PREVIEW · {preview.report.reportDate}</span><h2>Premarket intelligence</h2></div><button className="icon-button" title="Close report preview" onClick={() => setPreview(null)}><X size={18} /></button></div><div className="preview-meta"><span className="tag tag-demo">{preview.report.mode?.toUpperCase()}</span><span>As of {formatTimestamp(preview.report.dataAsOf)}</span></div>{preview.report.sections.map((item) => <div className="preview-section" key={item.title}><div><strong>{item.title}</strong><span className={`tag tag-${item.status}`}>{item.status}</span></div>{item.items.length ? item.items.map((stock) => <p key={stock.symbol}>{stock.symbol} · {formatMoney(stock.price)} · {formatPercent(stock.changePercent)} · RVOL {stock.relativeVolume ?? "--"}</p>) : <p className="muted-text">No data available from the configured sources.</p>}</div>)}<div className="limitations-box"><AlertTriangle size={16} /><p>{preview.report.limitations.join(" ")}</p></div><div className="modal-actions"><button className="button button-quiet" onClick={() => setPreview(null)}>Close</button><button className="button button-primary" onClick={() => { setPreview(null); void sendReport(); }}><Send size={15} /> Send report</button></div></section></div>}
    </main>
  );
}