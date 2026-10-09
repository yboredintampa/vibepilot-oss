import React, { useEffect, useState } from "react";

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

type BrandProfile = {
  business_name: string;
  city: string;
  state: string;
  industry: string;
  voice: string;
};

type PostHistoryItem = {
  id: string;
  body_text: string;
  created_at: string;
};

function SectionCard(props: {
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl bg-neutral-900/60 border border-neutral-800 shadow-xl p-6 flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-neutral-100">
          {props.title}
        </h2>
      </div>
      <div className="text-neutral-300 text-sm leading-relaxed">
        {props.children}
      </div>
      {props.footer && (
        <div className="pt-4 border-t border-neutral-800 text-sm text-neutral-400 flex flex-wrap gap-2">
          {props.footer}
        </div>
      )}
    </div>
  );
}

function VPButton(props: {
  children: React.ReactNode;
  onClick?: () => void;
  loading?: boolean;
  variant?: "solid" | "soft" | "ghost";
}) {
  const { children, onClick, loading, variant = "solid" } = props;

  const base =
    "text-xs font-medium rounded-lg px-3 py-2 transition-colors border";

  const styles: Record<string, string> = {
    solid:
      "bg-emerald-500/20 border-emerald-400/30 text-emerald-300 hover:bg-emerald-500/30 hover:text-emerald-200",
    soft:
      "bg-neutral-800 border-neutral-700 text-neutral-200 hover:bg-neutral-700 hover:text-white",
    ghost:
      "bg-transparent border-neutral-800 text-neutral-400 hover:bg-neutral-800/40 hover:text-neutral-200",
  };

  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`${base} ${styles[variant]} disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {loading ? "…" : children}
    </button>
  );
}

function App() {
  const [loading, setLoading] = useState(true);

  // auth / session
  const [whoami, setWhoami] = useState<any>(null);

  // brand
  const [brand, setBrand] = useState<BrandProfile | null>(null);

  // draft post preview
  const [draft, setDraft] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);

  // publish
  const [publishLoading, setPublishLoading] = useState(false);

  // history
  const [history, setHistory] = useState<PostHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  // tiny toast
  const [toast, setToast] = useState<string | null>(null);
  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  // helper to hit FastAPI with cookie (base URL from VITE_API_BASE_URL)
  async function api(path: string, opts?: RequestInit) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(opts && opts.headers),
      },
      ...opts,
    });

    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Request failed: ${res.status}`);
    }
    return res.json();
  }

  async function fetchHistory() {
    setHistoryLoading(true);
    try {
      const data = await api("/content/history", { method: "GET" });
      if (data && data.history && Array.isArray(data.history)) {
        setHistory(data.history);
      } else {
        setHistory([]);
      }
    } catch (err) {
      console.error("history error", err);
      showToast("Couldn't load history");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function fetchBrand() {
    try {
      const data = await api("/brand/me");
      if (data && data.brand) {
        setBrand({
          business_name: data.brand.business_name,
          city: data.brand.city,
          state: data.brand.state,
          industry: data.brand.industry,
          voice: data.brand.voice,
        });
      }
    } catch (err) {
        console.error("brand error", err);
        // it's fine if no brand yet
    }
  }

  async function handleGeneratePreview() {
    setPreviewLoading(true);
    try {
      const data = await api("/content/preview", { method: "POST" });
      if (data && data.preview && data.preview.text) {
        setDraft(data.preview.text);
        showToast("Generated new post ✨");
      } else {
        showToast("No preview returned");
      }
    } catch (err) {
      console.error("preview error", err);
      showToast("Couldn't generate preview");
    } finally {
      setPreviewLoading(false);
    }
  }

  async function handlePublish() {
    if (!draft.trim()) {
      showToast("Nothing to publish");
      return;
    }
    setPublishLoading(true);
    try {
      const data = await api("/content/publish", {
        method: "POST",
        body: JSON.stringify({ text: draft }),
      });

      if (data && data.published) {
        showToast("Published ✅");
        fetchHistory();
      } else {
        showToast("Publish failed");
      }
    } catch (err) {
      console.error("publish error", err);
      showToast("Couldn't publish");
    } finally {
      setPublishLoading(false);
    }
  }

  // boot sequence
  useEffect(() => {
    (async () => {
      try {
        // 1. login demo (sets cookie in browser)
        await api("/auth/login-demo", {
          method: "POST",
          body: JSON.stringify({ email: "you@example.com" }),
        });

        // 2. whoami
        const w = await api("/auth/whoami");
        setWhoami(w.claims ?? w);

        // 3. brand
        await fetchBrand();

        // 4. preview (draft content)
        try {
          const data = await api("/content/preview", { method: "POST" });
          if (data && data.preview && data.preview.text) {
            setDraft(data.preview.text);
          }
        } catch {
          /* can ignore preview fail here */
        }

        // 5. history
        await fetchHistory();
      } catch (err) {
        console.error("initial load error", err);
        showToast("Startup failed");
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-b from-neutral-950 via-neutral-900 to-black text-neutral-100 p-6">
      {/* toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-neutral-800 border border-neutral-700 text-neutral-100 text-sm rounded-lg px-4 py-2 shadow-xl">
          {toast}
        </div>
      )}

      <div className="max-w-6xl mx-auto flex flex-col gap-8">
        {/* HEADER */}
        <header className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="text-xl font-semibold text-white tracking-[-0.03em] flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
              VibePilot
            </div>
            <div className="text-sm text-neutral-400 mt-1">
              AI Social Engine for {brand?.business_name || "your business"}
            </div>
          </div>

          <div className="text-right text-xs text-neutral-500">
            <div>
              {whoami
                ? `tenant ${whoami.tenant_id?.slice?.(0, 8)}…`
                : "not signed in"}
            </div>
            <div className="text-neutral-600">
              {new Date().toLocaleString()}
            </div>
          </div>
        </header>

        {/* MAIN GRID */}
        <main className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* BRAND CARD */}
          <SectionCard
            title="Your Brand"
            footer={
              <>
                <VPButton
                  variant="soft"
                  onClick={fetchBrand}
                >
                  Refresh
                </VPButton>
              </>
            }
          >
            {brand ? (
              <div className="text-sm leading-relaxed text-neutral-200">
                <div className="font-medium text-neutral-100 text-base">
                  {brand.business_name}
                </div>
                <div className="text-neutral-400">
                  {brand.city}, {brand.state}
                </div>

                <div className="mt-4 flex flex-col gap-2 text-xs">
                  <div className="flex items-start gap-2">
                    <span className="text-neutral-500 min-w-[4rem]">
                      Industry
                    </span>
                    <span className="text-neutral-300">
                      {brand.industry || "–"}
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-neutral-500 min-w-[4rem]">
                      Voice
                    </span>
                    <span className="text-neutral-300">
                      {brand.voice || "–"}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-neutral-500 text-sm">
                No brand set yet.
                <br />
                Call /brand/setup from backend first.
              </div>
            )}
          </SectionCard>

          {/* DRAFT / PREVIEW CARD */}
          <SectionCard
            title="Post Draft"
            footer={
              <>
                <VPButton
                  variant="soft"
                  onClick={handleGeneratePreview}
                  loading={previewLoading}
                >
                  Generate post
                </VPButton>

                <VPButton
                  variant="solid"
                  onClick={handlePublish}
                  loading={publishLoading}
                >
                  Publish
                </VPButton>
              </>
            }
          >
            {loading ? (
              <div className="text-neutral-500 text-sm">
                Loading preview…
              </div>
            ) : (
              <textarea
                className="w-full h-40 bg-neutral-950/40 border border-neutral-800 rounded-xl p-3 text-neutral-100 text-sm outline-none focus:ring-2 focus:ring-emerald-500/40 focus:border-emerald-400/40 resize-none"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            )}

            <div className="text-[10px] text-neutral-500">
              This is what would go on Facebook right now.
            </div>
          </SectionCard>

          {/* HISTORY CARD */}
          <SectionCard
            title="Published History"
            footer={
              <>
                <VPButton
                  variant="ghost"
                  onClick={fetchHistory}
                  loading={historyLoading}
                >
                  Refresh History
                </VPButton>
              </>
            }
          >
            {historyLoading ? (
              <div className="text-neutral-500 text-sm">
                Loading history…
              </div>
            ) : history.length === 0 ? (
              <div className="text-neutral-500 text-sm">
                No posts published yet.
              </div>
            ) : (
              <div className="flex flex-col gap-4 max-h-56 overflow-y-auto pr-1">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="bg-neutral-950/40 border border-neutral-800 rounded-xl p-3"
                  >
                    <div className="text-[10px] text-neutral-500 flex items-center justify-between">
                      <span>ID {item.id.slice(0, 8)}…</span>
                      <span>
                        {new Date(item.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="text-neutral-200 text-sm leading-relaxed mt-2 whitespace-pre-line">
                      {item.body_text}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </main>

        {/* FOOTER NOTE */}
        <footer className="text-center text-[10px] text-neutral-600 pt-4 pb-8">
          <span className="text-neutral-500">
            Built for local service owners.
          </span>{" "}
          <span className="text-neutral-700">Automatic, daily, on-brand.</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
