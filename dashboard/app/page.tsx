"use client";

import { useEffect, useState } from "react";

type Lead = {
  id: string;
  createdTime: string;
  name: string;
  company: string;
  source: string;
  contact: string;
  score: number;
  notes: string;
  autoSourced: boolean;
};

type Tab = "Overview" | "Leads" | "Discover" | "Analytics";

type SearchRun = {
  requestId: string;
  keyword: string;
  searchLimit: string;
  status: "queued" | "in_progress" | "completed" | "failed";
  message: string;
  createdAt: string;
  runUrl?: string;
  artifactAvailable?: boolean;
  artifactId?: number | null;
};

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [keyword, setKeyword] = useState("");
  const [searchLimit, setSearchLimit] = useState("25");
  const [searching, setSearching] = useState(false);
  const [searchMessage, setSearchMessage] = useState("");
  const [searchHistory, setSearchHistory] = useState<SearchRun[]>([]);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);

  // Restore this browser session's search history.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem("leadgen-search-history");
      if (saved) setSearchHistory(JSON.parse(saved) as SearchRun[]);
    } catch (error) {
      console.error("Could not restore search history:", error);
    }
  }, []);

  // Keep the history scoped to the current browser tab session.
  useEffect(() => {
    try {
      sessionStorage.setItem(
        "leadgen-search-history",
        JSON.stringify(searchHistory)
      );
    } catch (error) {
      console.error("Could not save search history:", error);
    }
  }, [searchHistory]);

  // Poll GitHub Actions for every search that is still queued or running.
  useEffect(() => {
    const activeRuns = searchHistory.filter(
      (run) => run.status === "queued" || run.status === "in_progress"
    );
    if (activeRuns.length === 0) return;

    let cancelled = false;

    const checkRuns = async () => {
      await Promise.all(
        activeRuns.map(async (run) => {
          try {
            const response = await fetch(
              `/api/search-status?requestId=${encodeURIComponent(run.requestId)}`,
              { cache: "no-store" }
            );
            const data = await response.json();
            if (!response.ok || !data.success || cancelled) return;

            const nextStatus =
              data.status === "completed" || data.status === "failed"
                ? data.status
                : data.status === "in_progress"
                  ? "in_progress"
                  : "queued";

            setSearchHistory((current) =>
              current.map((item) =>
                item.requestId === run.requestId
                  ? {
                      ...item,
                      status: nextStatus,
                      message: data.message || item.message,
                      runUrl: data.runUrl || item.runUrl,
                      artifactAvailable: Boolean(data.artifactAvailable),
                      artifactId: data.artifactId ?? item.artifactId ?? null,
                    }
                  : item
              )
            );

            if (nextStatus === "completed") {
              fetchLeads();
            }
          } catch (error) {
            console.error("Search status check failed:", error);
          }
        })
      );
    };

    checkRuns();
    const timer = window.setInterval(checkRuns, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [searchHistory]);

  async function fetchLeads() {
    try {
      setLoading(true);
      const response = await fetch("/api/leads");
      const data = await response.json();
      if (data.success) setLeads(data.leads ?? []);
    } catch (error) {
      console.error("Failed to fetch leads:", error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchLeads();
  }, []);

  async function startSearch(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!keyword.trim()) return;

    setSearching(true);
    setSearchMessage("");

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keyword: keyword.trim(), searchLimit }),
      });
      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.error || "Unable to start search.");
      }

      const newRun: SearchRun = {
        requestId: data.requestId,
        keyword: keyword.trim(),
        searchLimit,
        status: "queued",
        message: "Waiting for GitHub Actions to start.",
        createdAt: new Date().toISOString(),
      };

      setSearchHistory((current) => [newRun, ...current]);
      setSearchMessage("Search queued successfully. You can track its progress below.");
      setKeyword("");
    } catch (error) {
      setSearchMessage(
        error instanceof Error ? error.message : "Something went wrong."
      );
    } finally {
      setSearching(false);
    }
  }

  const totalLeads = leads.length;
  const highQuality = leads.filter((lead) => lead.score >= 75).length;
  const averageScore = totalLeads
    ? Math.round(leads.reduce((sum, lead) => sum + lead.score, 0) / totalLeads)
    : 0;

  const filteredLeads = leads.filter((lead) =>
    `${lead.name} ${lead.company} ${lead.contact}`
      .toLowerCase()
      .includes(search.toLowerCase())
  );

  const navItems: Tab[] = ["Overview", "Leads", "Discover", "Analytics"];

  return (
    <main className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-[#e9e3dc] bg-[#f8f5ef]/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-6 py-4 lg:px-12">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[#f52880] text-2xl text-white">
              ✳
            </div>
            <div>
              <h1 className="text-xl font-black tracking-tight">The Orcas</h1>
              <p className="text-xs font-medium text-[#287ba9]">Lead Intelligence</p>
            </div>
          </div>

          <nav className="hidden items-center gap-2 md:flex">
            {navItems.map((item) => (
              <button
                key={item}
                onClick={() => setActiveTab(item)}
                className={`rounded-full px-6 py-3 text-sm font-semibold transition ${
                  activeTab === item
                    ? "bg-[#f52880] text-white shadow-md shadow-pink-200"
                    : "text-[#555] hover:bg-[#ffe1ed]"
                }`}
              >
                {item}
              </button>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <button
              onClick={fetchLeads}
              title="Refresh leads"
              className="flex h-10 w-10 items-center justify-center rounded-full border border-[#e9e3dc] bg-white text-lg hover:bg-[#ffe1ed]"
            >
              ↻
            </button>
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#a9dcf5] font-bold text-[#174e70]">
              Y
            </div>
          </div>
        </div>

        <div className="flex gap-2 overflow-x-auto px-5 pb-3 md:hidden">
          {navItems.map((item) => (
            <button
              key={item}
              onClick={() => setActiveTab(item)}
              className={`whitespace-nowrap rounded-full px-4 py-2 text-xs font-semibold ${
                activeTab === item ? "bg-[#f52880] text-white" : "bg-white text-[#555]"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] px-6 py-10 lg:px-12">
        {activeTab === "Overview" && (
          <section>
            {/* Editorial hero */}
            <div className="relative mb-12 overflow-hidden rounded-[32px] border border-[#e9e3dc] bg-[#fffefa] px-6 py-14 text-center md:px-12 md:py-20">
              <div className="pointer-events-none absolute -right-24 -top-32 h-80 w-80 rounded-full border-[35px] border-[#a9dcf5]/30" />
              <div className="pointer-events-none absolute -bottom-32 -left-24 h-72 w-72 rounded-full border-[35px] border-[#f52880]/10" />

              <div className="relative z-10 mx-auto max-w-4xl">
                <p className="mb-6 text-xs font-black uppercase tracking-[0.25em] text-[#287ba9]">
                  Streetwear lead intelligence
                </p>

                <h2 className="text-4xl font-black leading-[1.1] tracking-tight md:text-7xl">
                  Find, analyse and
                  <br />
                  close <span className="text-[#f52880]">brand leads.</span>
                </h2>

                <p className="mx-auto mt-6 max-w-xl text-base leading-7 text-[#777] md:text-lg">
                  Automated discovery, enrichment and scoring for streetwear and apparel brands.
                </p>

                <div className="mt-7 flex flex-wrap justify-center gap-3">
                  <span className="rotate-[-3deg] rounded-full bg-[#a9dcf5] px-5 py-2 text-sm font-bold text-[#174e70]">
                    @streetwear
                  </span>
                  <span className="rotate-[2deg] rounded-full bg-[#f52880] px-5 py-2 text-sm font-bold text-white">
                    @apparel
                  </span>
                  <span className="rotate-[-2deg] rounded-full bg-[#ffe1ed] px-5 py-2 text-sm font-bold text-[#e91e70]">
                    @independentbrands
                  </span>
                </div>

                <div className="mx-auto mt-12 flex max-w-3xl items-center justify-center">
                  {[
                    { icon: "✳", bg: "#171717", color: "#f52880", rotate: "-12deg" },
                    { icon: "◈", bg: "#a9dcf5", color: "#174e70", rotate: "-7deg" },
                    { icon: "✦", bg: "#ffe1ed", color: "#f52880", rotate: "-3deg" },
                    { icon: "◉", bg: "#f52880", color: "#ffffff", rotate: "0deg" },
                    { icon: "✧", bg: "#e2f3fc", color: "#287ba9", rotate: "4deg" },
                    { icon: "✳", bg: "#171717", color: "#ffffff", rotate: "9deg" },
                    { icon: "✳", bg: "#a9dcf5", color: "#174e70", rotate: "13deg" },
                  ].map((card, index) => (
                    <div
                      key={index}
                      className="flex h-24 w-16 shrink-0 items-center justify-center rounded-2xl border-[3px] border-white text-3xl shadow-lg transition duration-300 hover:z-20 hover:-translate-y-4 md:h-40 md:w-28 md:text-5xl"
                      style={{
                        backgroundColor: card.bg,
                        color: card.color,
                        transform: `rotate(${card.rotate})`,
                        marginLeft: index === 0 ? 0 : "-10px",
                      }}
                    >
                      {card.icon}
                    </div>
                  ))}
                </div>

                <div className="mt-12 flex flex-wrap justify-center gap-4">
                  <button
                    onClick={() => setActiveTab("Discover")}
                    className="rounded-full bg-[#f52880] px-9 py-4 text-sm font-bold text-white shadow-lg shadow-pink-200 transition hover:-translate-y-1 hover:bg-[#db1768]"
                  >
                    Discover Leads →
                  </button>
                  <button
                    onClick={() => setActiveTab("Leads")}
                    className="rounded-full bg-[#dff1fb] px-9 py-4 text-sm font-bold text-[#174e70] transition hover:-translate-y-1 hover:bg-[#cceafb]"
                  >
                    View Database
                  </button>
                </div>
              </div>
            </div>

            <div className="mb-10">
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-[#287ba9]">
                Your command centre
              </p>
              <h2 className="text-3xl font-black tracking-tight md:text-4xl">
                Your pipeline, at a glance.
              </h2>
              <p className="mt-3 max-w-xl text-base leading-7 text-[#777]">
                Track the brands your discovery engine finds, enriches and qualifies.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Total leads" value={totalLeads} description="Brands in your database" color="pink" icon="◎" />
              <StatCard label="High quality" value={highQuality} description="Leads scoring 75 or higher" color="blue" icon="✳" />
              <StatCard label="Average score" value={averageScore} description="Overall lead quality" color="pink" icon="✳" />
              <StatCard
                label="Ad Library leads"
                value={leads.filter((l) => l.source.toLowerCase().includes("ad")).length}
                description="Discovered through advertising"
                color="blue"
                icon="◈"
              />
            </div>

            <div className="mt-8 grid gap-6 xl:grid-cols-3">
              <div className="rounded-[28px] border border-[#e9e3dc] bg-[#fffefa] p-7 xl:col-span-2">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-xl font-bold">Your lead pipeline</h3>
                    <p className="mt-1 text-sm text-[#888]">A snapshot of your current database.</p>
                  </div>
                  <button
                    onClick={() => setActiveTab("Leads")}
                    className="rounded-full bg-[#e2f3fc] px-5 py-2.5 text-sm font-semibold text-[#174e70] hover:bg-[#cceafb]"
                  >
                    View all leads →
                  </button>
                </div>

                <div className="mt-8 space-y-6">
                  <ProgressRow label="High quality" value={highQuality} total={totalLeads} color="#f52880" />
                  <ProgressRow label="Other leads" value={totalLeads - highQuality} total={totalLeads} color="#a9dcf5" />
                </div>

                <div className="mt-8 rounded-2xl bg-[#f8f5ef] p-5">
                  <p className="text-xs font-bold uppercase tracking-widest text-[#888]">Pipeline status</p>
                  <p className="mt-2 text-2xl font-bold">
                    {totalLeads === 0 ? "Waiting for leads" : `${highQuality} promising opportunities`}
                  </p>
                  <p className="mt-1 text-sm text-[#888]">Based on your current Airtable database.</p>
                </div>
              </div>

              <div className="relative overflow-hidden rounded-[28px] bg-[#f52880] p-7 text-white">
                <div className="absolute -right-12 -top-12 h-48 w-48 rounded-full border-[30px] border-white/10" />
                <div className="absolute -bottom-16 -left-10 h-48 w-48 rounded-full bg-white/10" />
                <div className="relative z-10">
                  <span className="text-4xl">✳</span>
                  <p className="mt-10 text-xs font-bold uppercase tracking-[0.2em] text-white/75">Ready to discover?</p>
                  <h3 className="mt-3 text-3xl font-black leading-tight">Find brands<br />worth knowing.</h3>
                  <p className="mt-4 text-sm leading-6 text-white/85">
                    Run a custom discovery search and let your automated pipeline qualify potential clients.
                  </p>
                  <button
                    onClick={() => setActiveTab("Discover")}
                    className="mt-8 rounded-full bg-white px-6 py-3 text-sm font-bold text-[#f52880] transition hover:bg-[#ffe1ed]"
                  >
                    Discover leads →
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-8 rounded-[28px] border border-[#e9e3dc] bg-[#fffefa] p-7">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-bold">Recent leads</h3>
                  <p className="mt-1 text-sm text-[#888]">Recently added brands from Airtable.</p>
                </div>
                <button onClick={() => setActiveTab("Leads")} className="text-sm font-bold text-[#f52880]">
                  See all →
                </button>
              </div>
              <LeadTable leads={leads.slice(0, 5)} loading={loading} onSelect={setSelectedLead} />
            </div>
          </section>
        )}

        {activeTab === "Leads" && (
          <section>
            <PageHeading
              eyebrow="Your database"
              title="The lead list."
              description="Every brand your discovery engine has found, enriched and evaluated."
            />
            <div className="mb-6 flex flex-col gap-3 sm:flex-row">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search brands, companies or contacts..."
                className="w-full rounded-full border border-[#e9e3dc] bg-white px-6 py-3 text-sm outline-none focus:border-[#f52880]"
              />
              <button onClick={fetchLeads} className="rounded-full bg-[#f52880] px-7 py-3 text-sm font-bold text-white hover:bg-[#db1768]">
                Refresh database
              </button>
            </div>
            <div className="rounded-[28px] border border-[#e9e3dc] bg-[#fffefa] p-6">
              <LeadTable leads={filteredLeads} loading={loading} onSelect={setSelectedLead} />
            </div>
          </section>
        )}

        {activeTab === "Discover" && (
          <section>
            <PageHeading
              eyebrow="Automated discovery"
              title="Find something new."
              description="Enter a niche, keyword or brand category. Your scraper will search the Meta Ad Library, qualify potential leads and send them to Airtable."
            />
            <div className="grid gap-6 lg:grid-cols-3">
              <div className="rounded-[28px] border border-[#e9e3dc] bg-[#fffefa] p-8 lg:col-span-2">
                <div className="mb-8 flex h-14 w-14 items-center justify-center rounded-2xl bg-[#ffe1ed] text-3xl text-[#f52880]">✳</div>
                <h3 className="text-2xl font-bold">Start a discovery search</h3>
                <p className="mt-2 text-sm leading-6 text-[#888]">
                  Specify what kind of brands you want to find. Your search will be processed by your existing GitHub Actions workflow.
                </p>
                <form onSubmit={startSearch} className="mt-8">
                  <label htmlFor="keyword" className="mb-3 block text-sm font-bold">Search keyword</label>
                  <input
                    id="keyword"
                    value={keyword}
                    onChange={(e) => setKeyword(e.target.value)}
                    maxLength={100}
                    placeholder="e.g. Indian streetwear clothing"
                    className="w-full rounded-2xl border border-[#e9e3dc] bg-[#f8f5ef] px-5 py-4 text-sm outline-none transition focus:border-[#f52880]"
                  />
                  <div className="mt-3 flex justify-between text-xs text-[#999]">
                    <span>Be specific for better results.</span>
                    <span>{keyword.length}/100</span>
                  </div>
                  <label htmlFor="searchLimit" className="mb-3 mt-6 block text-sm font-bold">
                    Maximum brands to process
                  </label>
                  <select
                    id="searchLimit"
                    value={searchLimit}
                    onChange={(e) => setSearchLimit(e.target.value)}
                    className="w-full rounded-2xl border border-[#e9e3dc] bg-[#f8f5ef] px-5 py-4 text-sm outline-none transition focus:border-[#f52880] sm:max-w-xs"
                  >
                    <option value="10">10 brands</option>
                    <option value="25">25 brands (recommended)</option>
                    <option value="50">50 brands</option>
                    <option value="100">100 brands</option>
                  </select>
                  <p className="mt-2 text-xs text-[#999]">
                    This is the maximum number of unique brands the scraper will process. The number of qualified leads may be lower.
                  </p>
                  <button
                    type="submit"
                    disabled={searching || !keyword.trim()}
                    className="mt-6 w-full rounded-full bg-[#f52880] px-7 py-4 font-bold text-white transition hover:bg-[#db1768] disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
                  >
                    {searching ? "Submitting search..." : "Start discovery →"}
                  </button>
                </form>
                {searchMessage && (
                  <div className="mt-6 rounded-2xl bg-[#e2f3fc] p-4 text-sm font-medium text-[#174e70]">
                    {searchMessage}
                  </div>
                )}

                <div className="mt-10 border-t border-[#e9e3dc] pt-7">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-xl font-bold">Search activity</h3>
                      <p className="mt-1 text-sm text-[#888]">
                        Live status and exports from this browser session.
                      </p>
                    </div>
                    {searchHistory.length > 0 && (
                      <span className="rounded-full bg-[#ffe1ed] px-3 py-1.5 text-xs font-bold text-[#e91e70]">
                        {searchHistory.length} {searchHistory.length === 1 ? "search" : "searches"}
                      </span>
                    )}
                  </div>

                  {searchHistory.length === 0 ? (
                    <div className="mt-5 rounded-2xl bg-[#f8f5ef] p-5 text-sm text-[#888]">
                      Your searches will appear here once you start one.
                    </div>
                  ) : (
                    <div className="mt-5 space-y-3">
                      {searchHistory.map((run) => (
                        <div
                          key={run.requestId}
                          className="rounded-2xl border border-[#e9e3dc] bg-white p-5"
                        >
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="break-words font-bold">{run.keyword}</p>
                              <p className="mt-1 text-xs text-[#999]">
                                Up to {run.searchLimit} brands · {new Date(run.createdAt).toLocaleString()}
                              </p>
                            </div>
                            <span
                              className={`rounded-full px-3 py-1.5 text-xs font-bold ${
                                run.status === "completed"
                                  ? "bg-[#e2f3fc] text-[#174e70]"
                                  : run.status === "failed"
                                    ? "bg-[#ffe1ed] text-[#e91e70]"
                                    : "bg-[#f8f5ef] text-[#777]"
                              }`}
                            >
                              {run.status === "in_progress"
                                ? "RUNNING"
                                : run.status.toUpperCase()}
                            </span>
                          </div>
                          <p className="mt-3 text-sm text-[#777]">{run.message}</p>
                          <div className="mt-4 flex flex-wrap gap-3">
                            {run.artifactAvailable && run.artifactId && (
                              <a
                                href={`/api/download/${run.artifactId}`}
                                className="rounded-full bg-[#f52880] px-5 py-2.5 text-xs font-bold text-white transition hover:bg-[#db1768]"
                              >
                                Download Excel ↓
                              </a>
                            )}
                            {run.runUrl && (
                              <a
                                href={run.runUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="rounded-full bg-[#e2f3fc] px-5 py-2.5 text-xs font-bold text-[#174e70] hover:bg-[#cceafb]"
                              >
                                View GitHub run ↗
                              </a>
                            )}
                            {run.status === "completed" && !run.artifactAvailable && (
                              <span className="text-xs text-[#999]">
                                No Excel export was produced for this search.
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-[28px] bg-[#a9dcf5] p-8 text-[#174e70]">
                <p className="text-xs font-bold uppercase tracking-widest">How it works</p>
                <div className="mt-8 space-y-7">
                  <ProcessStep number="01" title="Discover" description="Apify searches the Meta Ad Library for matching brands." />
                  <ProcessStep number="02" title="Qualify" description="Groq evaluates potential leads and assigns scores." />
                  <ProcessStep number="03" title="Enrich" description="Your scraper gathers additional contact information." />
                  <ProcessStep number="04" title="Store" description="Qualified leads are added to your Airtable database." />
                </div>
              </div>
            </div>
          </section>
        )}

        {activeTab === "Analytics" && (
          <section>
            <PageHeading
              eyebrow="Performance insights"
              title="Know your numbers."
              description="An overview of the quality and composition of your lead database."
            />
            <div className="grid gap-4 sm:grid-cols-3">
              <StatCard label="Total leads" value={totalLeads} description="All recorded leads" color="pink" icon="◎" />
              <StatCard label="Average score" value={averageScore} description="Out of 100" color="blue" icon="✳" />
              <StatCard
                label="High quality rate"
                value={totalLeads ? `${Math.round((highQuality / totalLeads) * 100)}%` : "0%"}
                description="Leads scoring 75+"
                color="pink"
                icon="✳"
              />
            </div>

            <div className="mt-6 rounded-[28px] border border-[#e9e3dc] bg-[#fffefa] p-8">
              <h3 className="text-xl font-bold">Lead score distribution</h3>
              <p className="mt-1 text-sm text-[#888]">Breakdown by qualification score.</p>
              <div className="mt-8 space-y-6">
                {[
                  { label: "Excellent · 75–100", count: leads.filter((l) => l.score >= 75).length, color: "#f52880" },
                  { label: "Good · 50–74", count: leads.filter((l) => l.score >= 50 && l.score < 75).length, color: "#a9dcf5" },
                  { label: "Low · 0–49", count: leads.filter((l) => l.score < 50).length, color: "#d8d2ca" },
                ].map((item) => (
                  <ProgressRow key={item.label} label={item.label} value={item.count} total={totalLeads} color={item.color} />
                ))}
              </div>
            </div>
          </section>
        )}
      </div>

      {selectedLead && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-5"
          onClick={() => setSelectedLead(null)}
        >
          <div
            className="w-full max-w-lg rounded-[28px] bg-[#fffefa] p-8 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-[#287ba9]">Lead details</p>
                <h3 className="mt-2 text-2xl font-black">{selectedLead.company || selectedLead.name}</h3>
              </div>
              <button onClick={() => setSelectedLead(null)} className="rounded-full bg-[#ffe1ed] px-3 py-2 text-[#f52880]">×</button>
            </div>
            <div className="mt-7 space-y-5">
              <DetailRow label="Lead name" value={selectedLead.name} />
              <DetailRow label="Company" value={selectedLead.company} />
              <DetailRow label="Source" value={selectedLead.source} />
              <DetailRow label="Contact" value={selectedLead.contact} />
              <DetailRow
                label="Added"
                value={selectedLead.createdTime ? new Date(selectedLead.createdTime).toLocaleDateString() : "Unknown"}
              />
              <DetailRow label="Lead score" value={`${selectedLead.score}/100`} />
              <DetailRow label="Notes" value={selectedLead.notes} />
            </div>
          </div>
        </div>
      )}

      <footer className="border-t border-[#e9e3dc] py-7 text-center text-xs text-[#999]">
        THE ORCAS © 2026 · BUILT FOR BETTER DISCOVERY.
      </footer>
    </main>
  );
}

function PageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="mb-10">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.2em] text-[#287ba9]">{eyebrow}</p>
      <h2 className="text-4xl font-black tracking-tight md:text-6xl">{title}</h2>
      <p className="mt-4 max-w-2xl text-base leading-7 text-[#777]">{description}</p>
    </div>
  );
}

function StatCard({
  label,
  value,
  description,
  color,
  icon,
}: {
  label: string;
  value: string | number;
  description: string;
  color: "pink" | "blue";
  icon: string;
}) {
  return (
    <div className="rounded-[24px] border border-[#e9e3dc] bg-[#fffefa] p-6 transition hover:-translate-y-1 hover:shadow-lg hover:shadow-black/5">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-[#777]">{label}</p>
        <span className={`flex h-10 w-10 items-center justify-center rounded-xl text-xl ${
          color === "pink" ? "bg-[#ffe1ed] text-[#f52880]" : "bg-[#e2f3fc] text-[#287ba9]"
        }`}>
          {icon}
        </span>
      </div>
      <p className="mt-5 text-4xl font-black tracking-tight">{value}</p>
      <p className="mt-2 text-xs text-[#999]">{description}</p>
    </div>
  );
}

function ProgressRow({
  label,
  value,
  total,
  color,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
}) {
  const percentage = total > 0 ? (value / total) * 100 : 0;
  return (
    <div>
      <div className="mb-3 flex justify-between text-sm">
        <span className="font-semibold">{label}</span>
        <span className="text-[#888]">{value} · {Math.round(percentage)}%</span>
      </div>
      <div className="h-3 overflow-hidden rounded-full bg-[#f0ece6]">
        <div className="h-full rounded-full transition-all" style={{ width: `${percentage}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function LeadTable({
  leads,
  loading,
  onSelect,
}: {
  leads: Lead[];
  loading: boolean;
  onSelect: (lead: Lead) => void;
}) {
  if (loading) {
    return <div className="py-12 text-center text-sm text-[#888]">Loading your leads...</div>;
  }

  if (leads.length === 0) {
    return (
      <div className="py-12 text-center">
        <p className="text-lg font-bold">No leads found.</p>
        <p className="mt-2 text-sm text-[#999]">Your Airtable database is currently empty or there are no matches.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[650px] text-left">
        <thead>
          <tr className="border-b border-[#e9e3dc] text-xs uppercase tracking-wider text-[#999]">
            <th className="pb-4 font-semibold">Company</th>
            <th className="pb-4 font-semibold">Source</th>
            <th className="pb-4 font-semibold">Score</th>
            <th className="pb-4 font-semibold">Added</th>
            <th className="pb-4 font-semibold">Details</th>
          </tr>
        </thead>
        <tbody>
          {leads.map((lead) => (
            <tr key={lead.id} className="border-b border-[#f0ece6] last:border-0">
              <td className="py-5 pr-4">
                <p className="font-bold">{lead.company || lead.name || "Unknown"}</p>
                <p className="mt-1 text-xs text-[#999]">{lead.name}</p>
              </td>
              <td className="py-5 pr-4 text-sm text-[#777]">{lead.source || "Unknown"}</td>
              <td className="py-5 pr-4">
                <span className={`rounded-full px-3 py-1.5 text-xs font-bold ${
                  lead.score >= 75 ? "bg-[#ffe1ed] text-[#e91e70]" : lead.score >= 50 ? "bg-[#e2f3fc] text-[#287ba9]" : "bg-[#f0ece6] text-[#777]"
                }`}>
                  {lead.score}/100
                </span>
              </td>
              <td className="py-5 pr-4 text-sm text-[#888]">
                {lead.createdTime ? new Date(lead.createdTime).toLocaleDateString() : "—"}
              </td>
              <td className="py-5">
                <button onClick={() => onSelect(lead)} className="text-sm font-bold text-[#f52880] hover:underline">
                  View →
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProcessStep({
  number,
  title,
  description,
}: {
  number: string;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-4">
      <span className="text-sm font-black opacity-60">{number}</span>
      <div>
        <h4 className="font-bold">{title}</h4>
        <p className="mt-1 text-sm leading-5 text-[#174e70]/75">{description}</p>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-b border-[#e9e3dc] pb-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-[#999]">{label}</p>
      <p className="mt-1 break-words text-sm font-medium">{value || "Not available"}</p>
    </div>
  );
}