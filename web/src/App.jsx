import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BadgeCheck,
  BarChart3,
  Bell,
  Calculator,
  ChevronRight,
  CircleDollarSign,
  Clock3,
  ExternalLink,
  FileSearch,
  Gauge,
  Gem,
  LayoutDashboard,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  ServerCog,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Store,
  TrendingUp,
  X,
} from "lucide-react";

const courts = {
  slb: "서울",
  swb: "수원",
  bsb: "부산",
  dgb: "대구",
  djb: "대전",
  gjb: "광주",
};

const formatMoney = (value) => {
  if (value === null || value === undefined) return "분석 전";
  if (Math.abs(value) >= 100_000_000) return `${(value / 100_000_000).toFixed(1)}억원`;
  if (Math.abs(value) >= 10_000) return `${Math.round(value / 10_000).toLocaleString("ko-KR")}만원`;
  return `${Number(value).toLocaleString("ko-KR")}원`;
};

const formatTime = (value) => {
  if (!value) return "아직 없음";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
};

const priorityLabel = { high: "우선 검토", medium: "검토", watch: "관찰" };

function StatCard({ icon: Icon, label, value, note, tone = "navy" }) {
  return (
    <article className={`stat-card stat-${tone}`}>
      <div className="stat-icon"><Icon size={19} aria-hidden="true" /></div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        <span>{note}</span>
      </div>
    </article>
  );
}

function SourceStatus({ source }) {
  const status = source.status || "never";
  return (
    <article className="source-card">
      <div className="source-head">
        <span className={`status-dot ${status}`} aria-hidden="true" />
        <strong>{source.court_name}</strong>
        <span className={`source-tag ${status}`}>
          {status === "healthy" ? "정상" : status === "error" ? "점검 필요" : "미수집"}
        </span>
      </div>
      <div className="source-metrics">
        <span><b>{source.rows_seen || 0}</b>건 감지</span>
        <span><b>{source.latency_ms ? `${(source.latency_ms / 1000).toFixed(1)}s` : "—"}</b> 응답</span>
      </div>
      <p>{source.last_success_at ? `${formatTime(source.last_success_at)} 성공` : "수집을 시작하면 상태가 기록됩니다."}</p>
    </article>
  );
}

function OpportunityRow({ item, active, onSelect }) {
  const score = item.source?.score ?? item.score ?? 0;
  const displayScore = item.valuation_confidence || Math.min(96, 48 + score * 9);
  return (
    <button className={`opportunity-row ${active ? "active" : ""}`} onClick={() => onSelect(item)}>
      <span className={`priority-mark ${item.priority}`} />
      <span className="opportunity-main">
        <span className="opportunity-title">{item.title}</span>
        <span className="opportunity-meta">
          <b>{courts[item.court_code] || item.court_name}</b>
          <i />
          {item.asset_type || "미분류"}
          <i />
          {item.agency?.replace("채무자 ", "").slice(0, 27) || "매각기관 확인 필요"}
        </span>
      </span>
      <span className="price-cell">
        <small>최대 입찰가</small>
        <b>{formatMoney(item.max_bid_price)}</b>
      </span>
      <span className="price-cell profit">
        <small>예상 이익</small>
        <b>{formatMoney(item.expected_profit)}</b>
      </span>
      <span className="score-cell">
        <b>{displayScore}</b><small>/100</small>
      </span>
      <ChevronRight size={18} aria-hidden="true" />
    </button>
  );
}

function DetailPanel({ item, detail, onClose, onComparableSaved, onValuationSaved }) {
  const [form, setForm] = useState({ source: "당근", title: "", price: "", condition_label: "중고 A급", source_url: "" });
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const comparableCount = detail?.comparables?.length ?? item?.comparable_count ?? 0;
  const valuation = detail?.valuation || (item?.max_bid_price ? item : null);

  useEffect(() => {
    setForm((current) => ({ ...current, title: item?.title || "", price: "", source_url: "" }));
    setMessage("");
  }, [item?.id]);

  if (!item) return null;

  const saveComparable = async (event) => {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch(`/api/listings/${item.id}/comparables`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, price: Number(form.price), source_url: form.source_url || null }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "시세 저장에 실패했습니다.");
      setForm((current) => ({ ...current, price: "", source_url: "" }));
      setMessage("시세 근거를 저장했습니다.");
      await onComparableSaved(item.id);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  };

  const calculate = async () => {
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch(`/api/listings/${item.id}/valuation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ assumptions: {} }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "분석에 실패했습니다.");
      setMessage("최대 입찰가와 판매가를 다시 계산했습니다.");
      await onValuationSaved(item.id);
    } catch (error) {
      setMessage(error.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <aside className="detail-panel" aria-label="선택 공고 분석">
      <div className="detail-topline">
        <span className={`priority-pill ${item.priority}`}>{priorityLabel[item.priority] || "관찰"}</span>
        <button className="icon-button close-mobile" onClick={onClose} aria-label="상세 닫기"><X size={18} /></button>
      </div>
      <h2>{item.title}</h2>
      <p className="detail-agency">{item.court_name} · {item.agency}</p>

      <div className="signal-card">
        <div className="signal-score" style={{ "--score": `${valuation?.confidence || Math.min(86, 42 + item.score * 9)}%` }}>
          <div><strong>{valuation?.confidence || Math.min(86, 42 + item.score * 9)}</strong><span>신뢰도</span></div>
        </div>
        <div>
          <span className="eyebrow">DEAL SIGNAL</span>
          <h3>{comparableCount >= 3 ? "입찰가 산정 가능" : "시세 근거 보강 필요"}</h3>
          <p>{comparableCount}건의 비교 시세 · {item.asset_type}</p>
        </div>
      </div>

      <div className="recommend-grid">
        <div><span>권장 판매가</span><strong>{formatMoney(valuation?.recommended_sale_price)}</strong></div>
        <div><span>최대 입찰가</span><strong className="accent">{formatMoney(valuation?.max_bid_price)}</strong></div>
        <div><span>예상 순이익</span><strong>{formatMoney(valuation?.expected_profit)}</strong></div>
        <div><span>시세 표본</span><strong>{comparableCount}건</strong></div>
      </div>

      <div className="evidence-block">
        <div className="section-heading compact">
          <div><span className="eyebrow">MARKET EVIDENCE</span><h3>중고 시세 근거</h3></div>
          <span>{comparableCount}/3 권장</span>
        </div>
        <div className="source-chips">
          {["당근", "번개장터", "중고나라"].map((source) => {
            const count = detail?.comparables?.filter((item) => item.source === source).length || 0;
            return <span key={source} className={count ? "filled" : ""}>{source}<b>{count}</b></span>;
          })}
        </div>
        <form className="comparable-form" onSubmit={saveComparable}>
          <label>
            <span>출처</span>
            <select value={form.source} onChange={(event) => setForm({ ...form, source: event.target.value })}>
              <option>당근</option><option>번개장터</option><option>중고나라</option><option>기타</option>
            </select>
          </label>
          <label>
            <span>판매 희망가</span>
            <input type="number" min="1" required placeholder="예: 850000" value={form.price} onChange={(event) => setForm({ ...form, price: event.target.value })} />
          </label>
          <label className="wide-field">
            <span>비교 매물명</span>
            <input required minLength="2" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
          </label>
          <button className="secondary-button wide-field" disabled={saving}><Plus size={16} /> 시세 근거 추가</button>
        </form>
        {message && <p className="form-message">{message}</p>}
      </div>

      <button className="primary-button full" onClick={calculate} disabled={saving || comparableCount < 1}>
        {saving ? <LoaderCircle className="spin" size={17} /> : <Calculator size={17} />}
        입찰가·판매가 다시 계산
      </button>
      <a className="source-link" href={item.source_url} target="_blank" rel="noreferrer">
        법원 공고 원문 확인 <ExternalLink size={15} />
      </a>
      <p className="legal-note"><ShieldCheck size={15} /> 추천가는 의사결정 보조값입니다. 입찰 전 실물·권리·세금·공고 조건을 확인하세요.</p>
    </aside>
  );
}

export default function App() {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [priority, setPriority] = useState("all");
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [section, setSection] = useState("opportunities");

  const loadDashboard = async () => {
    const response = await fetch("/api/dashboard");
    if (!response.ok) throw new Error("대시보드를 불러오지 못했습니다.");
    const payload = await response.json();
    setDashboard(payload);
    setSelected((current) => current ? payload.listings.find((item) => item.id === current.id) || payload.listings[0] : payload.listings[0]);
  };

  const loadDetail = async (id) => {
    if (!id) return;
    const response = await fetch(`/api/listings/${id}`);
    if (response.ok) setDetail(await response.json());
  };

  useEffect(() => {
    loadDashboard().catch((requestError) => setError(requestError.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setDetail(null);
    if (selected?.id) loadDetail(selected.id);
  }, [selected?.id]);

  const visibleListings = useMemo(() => {
    const items = dashboard?.listings || [];
    const normalized = query.trim().toLowerCase();
    return items.filter((item) => {
      const matchPriority = priority === "all" || item.priority === priority;
      const searchable = `${item.title} ${item.agency} ${item.asset_type} ${item.court_name}`.toLowerCase();
      return matchPriority && (!normalized || searchable.includes(normalized));
    });
  }, [dashboard?.listings, priority, query]);

  const runScan = async () => {
    setScanning(true);
    setError("");
    try {
      const response = await fetch("/api/scans", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_pages: 2, enrich_details: false }),
      });
      if (!response.ok) throw new Error("수집을 시작하지 못했습니다.");
      await loadDashboard();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setScanning(false);
    }
  };

  const refreshDetail = async (id) => {
    await Promise.all([loadDetail(id), loadDashboard()]);
  };

  const stats = dashboard?.stats || {};
  const sources = dashboard?.sources || [];
  const healthyCount = sources.filter((source) => source.status === "healthy").length;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span><TrendingUp size={21} /></span><div><strong>리세일 레이더</strong><small>COURT ASSET INTELLIGENCE</small></div></div>
        <nav aria-label="주 메뉴">
          <button className={section === "opportunities" ? "active" : ""} onClick={() => setSection("opportunities")}><LayoutDashboard size={18} /> 기회 탐색</button>
          <button onClick={() => document.getElementById("market-workbench")?.scrollIntoView({ behavior: "smooth" })}><BarChart3 size={18} /> 시세 워크벤치</button>
          <button onClick={() => document.getElementById("source-health")?.scrollIntoView({ behavior: "smooth" })}><ServerCog size={18} /> 수집 상태</button>
          <button onClick={() => document.getElementById("source-health")?.scrollIntoView({ behavior: "smooth" })}><Activity size={18} /> 실행 이력</button>
        </nav>
        <div className="sidebar-divider" />
        <p className="nav-label">MONITORED SOURCES</p>
        <div className="court-list">
          {sources.map((source) => <span key={source.court_code}><i className={source.status} />{source.court_name.replace("회생법원", "")}</span>)}
        </div>
        <div className="sidebar-note"><Sparkles size={17} /><div><strong>매입 기준</strong><p>목표 마진 18% · 위험 버퍼 10%</p></div></div>
        <div className="sidebar-footer"><ShieldCheck size={15} /> 공개 공고 기반 의사결정 보조</div>
      </aside>

      <main>
        <header className="topbar">
          <div>
            <span className="eyebrow">TODAY'S SIGNALS</span>
            <h1>오늘의 매각 기회</h1>
          </div>
          <div className="top-actions">
            <div className="live-indicator"><span />{healthyCount}/{sources.length || 6} 소스 정상</div>
            <button className="icon-button" aria-label="알림"><Bell size={18} /></button>
            <button className="primary-button" onClick={runScan} disabled={scanning}>
              {scanning ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />}
              {scanning ? "전국 수집 중" : "지금 수집"}
            </button>
          </div>
        </header>

        {error && <div className="error-banner"><Activity size={17} />{error}<button onClick={() => setError("")}><X size={15} /></button></div>}

        <section className="stats-grid" aria-label="핵심 지표">
          <StatCard icon={FileSearch} label="누적 공고" value={`${stats.total || 0}건`} note="중복 없이 계속 누적" />
          <StatCard icon={Sparkles} label="신규 감지" value={`${stats.new_today || 0}건`} note="오늘 처음 확인된 공고" tone="gold" />
          <StatCard icon={Gauge} label="우선 검토" value={`${stats.high_count || 0}건`} note="전자제품·귀금속 중심" tone="green" />
          <StatCard icon={CircleDollarSign} label="건당 예상 이익" value={formatMoney(stats.avg_profit || 0)} note={`${stats.valued || 0}건 시세 분석 완료`} tone="purple" />
        </section>

        <section className="workspace" id="market-workbench">
          <div className="list-panel">
            <div className="section-heading">
              <div><span className="eyebrow">OPPORTUNITY PIPELINE</span><h2>수익 후보</h2></div>
              <span>{visibleListings.length}건</span>
            </div>
            <div className="toolbar">
              <label className="search-field"><Search size={17} /><input aria-label="공고 검색" placeholder="제품, 기관, 법원 검색" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
              <div className="filter-group" aria-label="우선순위 필터">
                {[['all', '전체'], ['high', '우선'], ['medium', '검토'], ['watch', '관찰']].map(([key, label]) => (
                  <button key={key} className={priority === key ? "active" : ""} onClick={() => setPriority(key)}>{label}</button>
                ))}
              </div>
              <button className="icon-button filter-button" aria-label="고급 필터"><SlidersHorizontal size={17} /></button>
            </div>

            <div className="table-labels"><span>공고·자산</span><span>최대 입찰가</span><span>예상 이익</span><span>신뢰도</span></div>
            <div className="opportunity-list">
              {loading ? (
                <div className="empty-state"><LoaderCircle className="spin" /><strong>데이터를 불러오는 중입니다</strong></div>
              ) : visibleListings.length ? (
                visibleListings.map((item) => <OpportunityRow key={item.id} item={item} active={selected?.id === item.id} onSelect={setSelected} />)
              ) : (
                <div className="empty-state"><FileSearch size={34} /><strong>아직 누적된 공고가 없습니다</strong><p>‘지금 수집’을 누르면 전국 6개 회생법원의 공개 공고를 확인합니다.</p><button className="secondary-button" onClick={runScan}>첫 수집 시작</button></div>
              )}
            </div>
          </div>

          <DetailPanel item={selected} detail={detail} onClose={() => setSelected(null)} onComparableSaved={refreshDetail} onValuationSaved={refreshDetail} />
        </section>

        <section className="health-section" id="source-health">
          <div className="section-heading">
            <div><span className="eyebrow">SENSING HEALTH</span><h2>전국 수집 상태</h2></div>
            <span className="health-summary"><BadgeCheck size={16} /> 법원별 장애 격리</span>
          </div>
          <div className="source-grid">{sources.map((source) => <SourceStatus key={source.court_code} source={source} />)}</div>
          <div className="history-strip">
            <div><Clock3 size={18} /><span>최근 실행</span><strong>{formatTime(dashboard?.runs?.[0]?.started_at)}</strong></div>
            <div><Store size={18} /><span>저장 방식</span><strong>SQLite 누적 이력</strong></div>
            <div><Gem size={18} /><span>감지 품목</span><strong>전자제품 · 귀금속 · 비품 · 설비</strong></div>
            <div><ShieldCheck size={18} /><span>마켓 시세</span><strong>검증한 링크·가격만 저장</strong></div>
          </div>
        </section>
      </main>
    </div>
  );
}
