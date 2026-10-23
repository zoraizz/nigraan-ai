import React from 'react'
import { Link } from 'react-router-dom'

export default function Overview() {
  const scrollTo = (id) => {
    const element = document.getElementById(id)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="-m-4 lg:-m-6 min-h-[calc(100vh-4rem)] bg-gradient-to-b from-[#0a301d] via-[#05170e] to-[#010603] px-6 py-10 md:py-16 text-slate-100 font-sans">
      <div className="mx-auto max-w-5xl space-y-20">

        {/* ── TOP HEADER & NAV ── */}
        <header className="border-b border-[#1b4a33] pb-8">
          <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-white leading-tight">
                Overview
              </h1>
              <p className="mt-3 text-sm md:text-base text-[#8aad9b] max-w-xl leading-relaxed">
                National flood surveillance, satellite damage detection, and humanitarian triage across Pakistan.
              </p>
            </div>

            <nav className="flex flex-wrap gap-x-6 gap-y-2 text-xs font-semibold tracking-wide uppercase">
              <button
                onClick={() => scrollTo('highest-risk')}
                className="text-[#6a9b84] hover:text-emerald-300 transition-colors cursor-pointer"
              >
                Risk Map
              </button>
              <button
                onClick={() => scrollTo('damage-assessment')}
                className="text-[#6a9b84] hover:text-emerald-300 transition-colors cursor-pointer"
              >
                Damage
              </button>
              <button
                onClick={() => scrollTo('aid-priority')}
                className="text-[#6a9b84] hover:text-emerald-300 transition-colors cursor-pointer"
              >
                Aid Priority
              </button>
              <button
                onClick={() => scrollTo('flood-tracker')}
                className="text-[#6a9b84] hover:text-emerald-300 transition-colors cursor-pointer"
              >
                Flood Tracker
              </button>
            </nav>
          </div>
        </header>

        {/* ── SECTION 1: HIGHEST AT RISK DISTRICT ── */}
        <section id="highest-risk" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-rose-400 uppercase">
              01 / Risk Map Spotlight
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Highest at Risk: Dadu, Sindh
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              Trapped between the Kirthar mountain range and Manchhar Lake, Dadu faces compound flood pressure from mountain torrents and Indus River backflow.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                When heavy rainfall strikes Balochistan, runoff cascades down the steep Kirthar hills directly into Dadu's western plains. At the same time, if the Indus River downstream is running near peak capacity at Sukkur Barrage, the Main Nara Valley Drain (MNVD) cannot discharge into the river, causing water to pool backward into Manchhar Lake.
              </p>
              <p>
                This dual pressure puts over 1.7 million residents, rural agricultural land, and primary transit corridors under extreme inundation threat before official river gauges even hit their highest warnings.
              </p>

              <div className="pt-2">
                <Link
                  to="/risk-map"
                  className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-emerald-300 border border-emerald-500/40 bg-[#071a0e] hover:bg-[#0e3a24] px-4 py-2 transition-colors"
                >
                  Inspect Dadu on the Risk Map →
                </Link>
              </div>
            </div>

            <div className="md:col-span-5 space-y-6 border-l border-[#1b4a33] pl-6 md:pl-8">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Assessed Risk Level</div>
                <div className="mt-1 font-mono text-4xl font-bold text-rose-400 tracking-tight">92%</div>
                <div className="text-xs text-slate-500 mt-1">Critical threshold across weather, soil &amp; drainage</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">90-Day Rainfall Memory</div>
                <div className="mt-1 font-mono text-2xl font-semibold text-white">284 mm</div>
                <div className="text-xs text-slate-500 mt-1">Ground is heavily saturated from seasonal storms</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">3-Day Forecast Rain</div>
                <div className="mt-1 font-mono text-2xl font-semibold text-cyan-300">+58.5 mm</div>
                <div className="text-xs text-slate-500 mt-1">Approaching monsoon front expected within 72 hours</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Vulnerable Population</div>
                <div className="mt-1 font-mono text-2xl font-semibold text-white">1,740,000</div>
                <div className="text-xs text-slate-500 mt-1">Residents living in direct floodway zones</div>
              </div>
            </div>
          </div>
        </section>

        <hr className="border-[#1b4a33]" />

        {/* ── SECTION 2: DAMAGE ASSESSMENT ── */}
        <section id="damage-assessment" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-purple-400 uppercase">
              02 / Computer Vision
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Damage Assessment
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              AI scene classification on orbital and aerial imagery, pinpointing submerged roads and destroyed settlements before rescue boats deploy.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                In a major flood, physical roads wash out and cellular towers go dark, leaving rescue agencies blind to ground conditions for days. Rather than waiting for manual field reports, Nigraan AI ingests raw satellite imagery and divides scenes into fine grid tiles.
              </p>
              <p>
                A deep-learning vision model classifies each tile into standing floodwater, structural destruction, or intact ground. This produces an immediate, verifiable damage percentage for every community, showing relief workers exactly where access routes have been severed.
              </p>

              <div className="pt-2">
                <Link
                  to="/damage-assessment"
                  className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-purple-300 border border-purple-500/40 bg-[#0d0a1a] hover:bg-[#1a1030] px-4 py-2 transition-colors"
                >
                  Launch Damage Assessment Tool →
                </Link>
              </div>
            </div>

            <div className="md:col-span-5 space-y-6 border-l border-[#1b4a33] pl-6 md:pl-8">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Method</div>
                <div className="mt-1 text-base font-semibold text-white leading-snug">Tiled Neural Scene Classifier</div>
                <div className="text-xs text-slate-500 mt-1">Adaptive grid overlays for pinpoint damage isolation</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">What It Detects</div>
                <div className="mt-1 text-base font-semibold text-white leading-snug">Water Extent, Road Cuts, Roof Loss</div>
                <div className="text-xs text-slate-500 mt-1">Distinguishes temporary pooling from structural destruction</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Processing Speed</div>
                <div className="mt-1 font-mono text-2xl font-semibold text-emerald-400">&lt; 1.2s</div>
                <div className="text-xs text-slate-500 mt-1">Instant inference per uploaded satellite scene</div>
              </div>
            </div>
          </div>
        </section>

        <hr className="border-[#1b4a33]" />

        {/* ── SECTION 3: AID PRIORITY ── */}
        <section id="aid-priority" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-amber-400 uppercase">
              03 / Decision Support
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Aid Priority
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              Data-driven relief dispatch schedules that direct supplies and medical teams to where needs are highest, free from guesswork or political bias.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                When emergency resources like clean drinking water, rescue rafts, and medical rations are limited, distributing aid on a first-come basis leaves the most isolated communities stranded.
              </p>
              <p>
                The Aid Priority algorithm evaluates every monitored district using three objective factors: 40% hazard risk severity, 40% verified satellite structural damage, and 20% exposed population density. The result is a transparent, ranked dispatch schedule updated continuously as new assessments arrive.
              </p>

              <div className="pt-2">
                <Link
                  to="/aid-priority"
                  className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-amber-300 border border-amber-500/40 bg-[#1a1000] hover:bg-[#2a1c00] px-4 py-2 transition-colors"
                >
                  View Full Aid Priority Schedule →
                </Link>
              </div>
            </div>

            <div className="md:col-span-5 space-y-4 border-l border-[#1b4a33] pl-6 md:pl-8">
              <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Current Top Priority Queue</div>

              <div className="space-y-3 pt-1">
                {[
                  { rank: '01', name: 'Rajanpur', province: 'Punjab', badge: 'Urgent', color: 'text-rose-400' },
                  { rank: '02', name: 'Dadu', province: 'Sindh', badge: 'Urgent', color: 'text-rose-400' },
                  { rank: '03', name: 'D.G. Khan', province: 'Punjab', badge: 'High', color: 'text-amber-400' },
                  { rank: '04', name: 'Jaffarabad', province: 'Balochistan', badge: 'High', color: 'text-amber-400' },
                ].map((item) => (
                  <div key={item.rank} className="flex items-baseline justify-between border-b border-[#1b4a33] pb-2">
                    <div>
                      <span className="font-mono text-xs text-amber-400 mr-2">{item.rank}</span>
                      <span className="font-semibold text-white text-sm">{item.name}</span>
                      <span className="text-xs text-[#6a9b84] ml-1.5">({item.province})</span>
                    </div>
                    <span className={`text-xs font-mono font-semibold ${item.color}`}>#{item.rank} {item.badge}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        <hr className="border-[#1b4a33]" />

        {/* ── SECTION 4: FLOOD TRACKER ── */}
        <section id="flood-tracker" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-blue-400 uppercase">
              04 / Hydrological Routing
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Flood Tracker
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              Physics-based flood wave routing down the 1,400-kilometer Indus River, calculating exact arrival times for barrages and 900+ downstream villages.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                When an upstream dam like Tarbela releases emergency floodwaters or torrential northern rainfall enters the river, that crest takes several days to travel down Pakistan. A peak at Taunsa Barrage takes roughly 48 hours to reach Guddu Barrage in upper Sindh, and nearly a week to reach Kotri near the Arabian Sea.
              </p>
              <p>
                Nigraan AI links discharge readings across 7 Indus barrages into discrete flood waves. It calculates hour-by-hour arrival windows for each settlement along the river and drafts emergency warnings in Urdu and Sindhi for immediate loudspeaker and SMS broadcast.
              </p>

              <div className="pt-2">
                <Link
                  to="/flood-tracker"
                  className="inline-flex items-center gap-2 text-xs font-semibold tracking-wide uppercase text-blue-300 border border-blue-500/40 bg-[#050d1a] hover:bg-[#0a1a2e] px-4 py-2 transition-colors"
                >
                  Open Indus Flood Tracker →
                </Link>
              </div>
            </div>

            <div className="md:col-span-5 space-y-6 border-l border-[#1b4a33] pl-6 md:pl-8">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Barrage in Focus</div>
                <div className="mt-1 text-xl font-bold text-white tracking-tight">Taunsa Barrage</div>
                <div className="text-xs text-rose-400 font-semibold mt-0.5">High Flood Stage (Outflow &gt; 500,000 cusecs)</div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Inflow</div>
                  <div className="mt-1 font-mono text-lg font-semibold text-white">567,000 cusecs</div>
                  <div className="text-xs text-rose-400">Rising Trend</div>
                </div>
                <div>
                  <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Outflow</div>
                  <div className="mt-1 font-mono text-lg font-semibold text-white">551,000 cusecs</div>
                  <div className="text-xs text-slate-500">Gates Fully Opened</div>
                </div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Downstream Impact Point</div>
                <div className="mt-1 text-sm font-semibold text-white">Guddu Barrage (208 km downstream)</div>
                <div className="mt-1 text-xs text-emerald-400 font-mono font-semibold">ETA: ~48 Hours (±12h arrival window)</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Last-Mile Warning Coverage</div>
                <div className="mt-1 text-sm font-semibold text-slate-200">926 mapped villages with Urdu &amp; Sindhi alert drafts</div>
              </div>
            </div>
          </div>
        </section>

      </div>
    </div>
  )
}
