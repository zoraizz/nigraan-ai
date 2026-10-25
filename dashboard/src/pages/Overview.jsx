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
                Hazard risk for 16 districts, Indus flood routing, damage assessment on uploaded satellite imagery, and aid prioritisation.
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
                onClick={() => scrollTo('flood-tracker')}
                className="text-[#6a9b84] hover:text-emerald-300 transition-colors cursor-pointer"
              >
                Flood Tracker
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
            </nav>
          </div>
        </header>

        {/* ── SECTION 1: HIGHEST AT RISK DISTRICT ── */}
        <section id="highest-risk" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-rose-400 uppercase">
              01 / Risk Map Spotlight
            </span>
            <span className="ml-3 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-amber-300">
              Scenario: monsoon peak
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
                The figures on the right are a fixed monsoon-peak scenario, not a live reading. Open the Risk Map for Dadu's current Risk Flag assessment.
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
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Scenario Risk Score</div>
                <div className="mt-1 font-mono text-4xl font-bold text-rose-400 tracking-tight">92%</div>
                <div className="text-xs text-slate-500 mt-1">Illustrative. Risk Flag itself returns low, medium or high</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">90-Day Rainfall Memory</div>
                <div className="mt-1 font-mono text-2xl font-semibold text-white">284 mm</div>
                <div className="text-xs text-slate-500 mt-1">Rain over the past 90 days</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">3-Day Forecast Rain</div>
                <div className="mt-1 font-mono text-2xl font-semibold text-cyan-300">+58.5 mm</div>
                <div className="text-xs text-slate-500 mt-1">Forecast rain over the next 3 days</div>
              </div>
            </div>
          </div>
        </section>

        <hr className="border-[#1b4a33]" />

        {/* ── SECTION 2: FLOOD TRACKER ── */}
        <section id="flood-tracker" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-blue-400 uppercase">
              02 / Hydrological Routing
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Flood Tracker
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              Empirical routing from 2022 peak-to-peak lags, with ETA windows, for 7 Indus barrages and 926 downstream villages.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                A flood crest takes days to travel down the Indus. In 2022, a peak at Taunsa Barrage took about 48 hours to reach Guddu Barrage in upper Sindh, and more than a week to reach Kotri.
              </p>
              <p>
                Nigraan AI routes a barrage peak downstream using the lags between barrage peaks measured in 2022. Each barrage and village gets an ETA window, and each village gets a short Urdu and Sindhi alert draft for an officer to review. Drafts are not sent automatically.
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
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Barrage in Focus · 2022 replay</div>
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
                  <div className="text-xs text-slate-500">2022 FFC reading</div>
                </div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Downstream Impact Point</div>
                <div className="mt-1 text-sm font-semibold text-white">Guddu Barrage (208 km downstream)</div>
                <div className="mt-1 text-xs text-emerald-400 font-mono font-semibold">ETA: ~48 hours (24–72 h window)</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Last-Mile Warning Coverage</div>
                <div className="mt-1 text-sm font-semibold text-slate-200">926 mapped villages, each with Urdu &amp; Sindhi alert drafts</div>
              </div>
            </div>
          </div>
        </section>

        <hr className="border-[#1b4a33]" />

        {/* ── SECTION 3: DAMAGE ASSESSMENT ── */}
        <section id="damage-assessment" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-purple-400 uppercase">
              03 / Computer Vision
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Damage Assessment
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              Building damage classification on uploaded satellite imagery: none, partial or destroyed.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                After a disaster, field reports can take days. An officer can upload a post-disaster satellite tile, or a larger scene that Nigraan AI splits into grid tiles.
              </p>
              <p>
                A ResNet-18 model rates building damage in each tile as none, partial or destroyed, and a scene reports the share of tiles in each class. Images that do not look like satellite imagery are marked uncertain and left out.
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
                <div className="mt-1 text-base font-semibold text-white leading-snug">Tiled Image Classifier</div>
                <div className="text-xs text-slate-500 mt-1">Large scenes are split into a grid of tiles</div>
              </div>

              <div>
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">What It Detects</div>
                <div className="mt-1 text-base font-semibold text-white leading-snug">Building Damage: None, Partial, Destroyed</div>
                <div className="text-xs text-slate-500 mt-1">One rating per tile</div>
              </div>
            </div>
          </div>
        </section>

        <hr className="border-[#1b4a33]" />

        {/* ── SECTION 4: AID PRIORITY ── */}
        <section id="aid-priority" className="space-y-6">
          <div>
            <span className="text-[10px] font-mono font-semibold tracking-widest text-amber-400 uppercase">
              04 / Decision Support
            </span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold tracking-tight text-white leading-snug">
              Aid Priority
            </h2>
            <p className="mt-2 text-sm text-[#8aad9b] max-w-2xl leading-relaxed">
              A ranked list of districts for relief dispatch, with the score behind each rank shown.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-10 md:grid-cols-12 pt-2">
            <div className="md:col-span-7 space-y-4 text-slate-300 text-sm leading-relaxed">
              <p>
                When emergency resources like clean drinking water, rescue rafts, and medical rations are limited, distributing aid on a first-come basis leaves the most isolated communities stranded.
              </p>
              <p>
                Aid Priority scores each district as 0.4 × risk + 0.6 × damage, from its Risk Flag level and its damage assessment, and ranks districts by that score.
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
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-[10px] font-mono uppercase tracking-wider text-[#6a9b84]">Top Priority Queue</div>
                <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-amber-300">
                  Scenario: monsoon peak
                </span>
              </div>

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


      </div>
    </div>
  )
}
