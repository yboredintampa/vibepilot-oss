import React, { useEffect, useMemo, useState } from "react";
import { Play, Pause, RotateCcw, Film, Video, Image as ImageIcon, Rocket, CheckCircle2, AlertTriangle } from "lucide-react";

// If you have shadcn/ui, swap these stubs for real components.
// Minimal inline styles so this file runs as-is.
const Button: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className="", ...props }) => (
  <button {...props} className={"px-3 py-2 rounded-xl bg-[#6C33FF] text-white hover:opacity-90 "+className}/>
);
const GhostButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement>> = ({ className="", ...props }) => (
  <button {...props} className={"px-3 py-2 rounded-xl bg-transparent text-[#E8E6FF] border border-[#2A1F43] hover:bg-[#120A1E] "+className}/>
);
const Switch: React.FC<{checked:boolean; onCheckedChange:(v:boolean)=>void}> = ({checked,onCheckedChange}) => (
  <label style={{display:'inline-flex',alignItems:'center',gap:8,cursor:'pointer'}}>
    <input type="checkbox" checked={checked} onChange={e=>onCheckedChange(e.target.checked)} />
    <span style={{color:'#C8C3F5'}}>Premium Video</span>
  </label>
);
const Input: React.FC<React.InputHTMLAttributes<HTMLInputElement>> = (props) => (
  <input {...props} className="w-full px-3 py-2 rounded-xl bg-transparent border border-[#2A1F43] text-[#E8E6FF]"/>
);
const Select: React.FC<{value:string; onChange:(v:string)=>void; options:{value:string,label:string}[]}> = ({value,onChange,options}) => (
  <select value={value} onChange={e=>onChange(e.target.value)} className="px-3 py-2 rounded-xl bg-transparent border border-[#2A1F43] text-[#E8E6FF]">
    {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>
);

type Asset = {
  kind: "image" | "video";
  name: string;
  path: string;
  size: number;
  mtime: number;
  url?: string | null;
};
type AssetsResp = { images: Asset[]; videos: Asset[]; }

const colors = {
  bg: "#0B0614",
  card: "#160D26",
  grid: "#2A1F43",
  text: "#E8E6FF",
  soft: "#C8C3F5",
  accent: "#6C33FF",
  glow: "#B09CFF",
  good: "#00D1B2",
  warn: "#F5A524",
};

const api = (path: string, init?: RequestInit) =>
  fetch(path, { headers: { "Content-Type": "application/json" }, ...init });

export default function VibePilotDashboard() {
  // UI state
  const [premium, setPremium] = useState(true);
  const [duration, setDuration] = useState("5");
  const [videoPrompt, setVideoPrompt] = useState("sunlit backyard pool, gentle water ripples, cinematic handheld, Sunnyvale");
  const [caption, setCaption] = useState("");
  const [posting, setPosting] = useState(true);

  // Assets
  const [assets, setAssets] = useState<AssetsResp>({ images: [], videos: [] });
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);

  // Feedback
  const [log, setLog] = useState<string[]>([]);
  const pushLog = (m: string) => setLog(l => [`${new Date().toLocaleTimeString()} ${m}`, ...l].slice(0, 50));

  // Theme init
  useEffect(() => {
    document.body.style.background = colors.bg;
    document.body.style.color = colors.text;
  }, []);

  const refreshAssets = async () => {
    const r = await api("/api/assets/latest");
    const data: AssetsResp = await r.json();
    setAssets(data);
  };

  useEffect(() => {
    refreshAssets();
  }, []);

  // Generate video
  const onGenerateVideo = async () => {
    if (!premium) {
      pushLog("Premium video toggled off.");
      return;
    }
    pushLog("Generating video…");
    const r = await api("/api/generate-video", {
      method: "POST",
      body: JSON.stringify({ prompt: videoPrompt, duration: Number(duration) }),
    });
    const data = await r.json();
    if (!data.ok) {
      pushLog(`❌ ${data.error || "Generation failed"}`);
    } else {
      pushLog(`✅ Video saved: ${data.path}`);
      await refreshAssets();
      setSelectedVideo(data.path || null);
    }
  };

  // Post now (auto picks video if selected/available else image else text)
  const onPostNow = async () => {
    pushLog("Posting to Facebook…");
    let payload: any = { caption: caption || undefined, asset_type: "auto" as const };
    if (premium && selectedVideo) {
      payload = { ...payload, asset_type: "video", video_path: selectedVideo };
    }
    const r = await api("/api/post-facebook", { method: "POST", body: JSON.stringify(payload) });
    const data = await r.json();
    if (!data.ok) {
      pushLog(`❌ Post failed: ${data.error || "Unknown error"}`);
    } else {
      const link = data.permalink_url || `https://facebook.com/${data.post_id || ""}`;
      pushLog(`✅ Posted: ${link}`);
    }
  };

  return (
    <div className="min-h-screen">
      <div className="max-w-6xl mx-auto p-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl grid place-items-center" style={{background: colors.accent+"22"}}>
              <Rocket size={16} style={{color: colors.glow}}/>
            </div>
            <div>
              <h1 className="text-xl font-semibold">VibePilot — Growth Command</h1>
              <p className="text-sm" style={{color: colors.soft}}>Calendar-first marketing autopilot • Sunnyvale, FL</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <GhostButton onClick={()=>window.location.reload()}><RotateCcw size={14}/> Refresh</GhostButton>
          </div>
        </div>

        {/* Controls */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          {/* Queue Manager */}
          <div className="lg:col-span-2 rounded-2xl border" style={{borderColor: colors.grid, background: colors.card}}>
            <div className="p-4">
              <div className="flex items-center gap-3 mb-3">
                <Film size={18} style={{color: colors.glow}}/>
                <div>
                  <div className="font-medium">Queue Manager</div>
                  <div className="text-sm" style={{color: colors.soft}}>Generate or attach a premium short video, then post.</div>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-2">
                  <div className="mb-2 text-sm" style={{color: colors.soft}}>Video Prompt</div>
                  <Input value={videoPrompt} onChange={(e)=>setVideoPrompt(e.target.value)} placeholder="Video prompt"/>
                </div>
                <div className="flex flex-col gap-2">
                  <div className="mb-2 text-sm" style={{color: colors.soft}}>Duration</div>
                  <Select value={duration} onChange={setDuration} options={[
                    {value:"5", label:"5s"},
                    {value:"8", label:"8s"},
                    {value:"10", label:"10s"},
                  ]}/>
                </div>
              </div>

              <div className="flex items-center gap-3 mt-3">
                <Switch checked={premium} onCheckedChange={setPremium}/>
                <GhostButton onClick={onGenerateVideo} className="flex items-center gap-2"><Video size={14}/> Generate Video</GhostButton>
              </div>

              <div className="mt-4">
                <div className="mb-2 text-sm" style={{color: colors.soft}}>Caption (optional)</div>
                <Input value={caption} onChange={(e)=>setCaption(e.target.value)} placeholder="Leave blank to auto-generate"/>
              </div>

              <div className="flex items-center gap-3 mt-4">
                <Button onClick={onPostNow} className="flex items-center gap-2"><CheckCircle2 size={16}/> Post Now</Button>
                <GhostButton onClick={()=>setPosting(p=>!p)} className="flex items-center gap-2">
                  {posting ? <Pause size={14}/> : <Play size={14}/>} {posting ? "Pause" : "Resume"}
                </GhostButton>
              </div>
            </div>
          </div>

          {/* Activity / Log */}
          <div className="rounded-2xl border p-4" style={{borderColor: colors.grid, background: colors.card}}>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={16} style={{color: colors.warn}}/>
              <div className="font-medium">Activity</div>
            </div>
            <div className="text-sm" style={{color: colors.soft, whiteSpace:'pre-wrap'}}>
              {log.length ? log.join("\n") : "No activity yet."}
            </div>
          </div>
        </div>

        {/* Media Gallery */}
        <div className="rounded-2xl border mt-6" style={{borderColor: colors.grid, background: colors.card}}>
          <div className="p-4">
            <div className="flex items-center gap-2 mb-4">
              <ImageIcon size={16} style={{color: colors.glow}}/>
              <div className="font-medium">Latest Media</div>
              <GhostButton onClick={refreshAssets} className="ml-auto">Refresh</GhostButton>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {assets.videos.slice(0,8).map(v => (
                <div key={v.name} className={`rounded-xl border ${selectedVideo===v.path?'ring-2 ring-[#6C33FF]':''}`} style={{borderColor: colors.grid, overflow:'hidden', cursor:'pointer'}} onClick={()=>setSelectedVideo(v.path)}>
                  <div className="p-2 text-xs" style={{color: colors.soft}}>{v.name}</div>
                  <video src={v.url || undefined} controls style={{width:'100%', background:'#000'}} />
                </div>
              ))}
              {assets.images.slice(0,8).map(i => (
                <div key={i.name} className="rounded-xl border" style={{borderColor: colors.grid, overflow:'hidden'}}>
                  <div className="p-2 text-xs" style={{color: colors.soft}}>{i.name}</div>
                  <img src={i.url || undefined} alt={i.name} style={{width:'100%', display:'block'}}/>
                </div>
              ))}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}

