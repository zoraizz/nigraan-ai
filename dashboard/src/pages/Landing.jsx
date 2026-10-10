import { Link } from 'react-router-dom'
import { useState, useEffect } from 'react'
import HeroMap from '../components/landing/HeroMap.jsx'
import HazardIcon from '../components/HazardIcon.jsx'
import Logo from '../components/layout/Logo.jsx'
import { DISTRICTS, HAZARD_TYPES } from '../config/districts.js'
import { FLOOD_2022_SOURCE, RESOURCES, SITE } from '../config/site.js'

const BG_IMAGES = [
  '/bg/bg1.jpg',   // flood — aerial submerged village
  '/bg/bg2.jpg',   // avalanche — mountain snow cloud
  '/bg/bg3.jpg',   // drought — cracked earth & sun
  '/bg/bg4.jpg',   // landslide — coastal cliff road collapse
  '/bg/bg5.jpg',   // mudslide — mountain road blocked
]

const NAV = [
  ['Vision', 'vision'],
  ['Overview', 'overview'],
  ['Why AI', 'why-ai'],
  ['About', 'about'],
  ['Contact', 'contact'],
  ['Resources', 'resources'],
]

// The four beats of the slogan, in order. This one really is a sequence.
const STEPS = [
  {
    verb: 'See',
    title: 'Risk',
    body: 'Rainfall signals and AI analysis flag where danger is building.',
  },
  {
    verb: 'Understand',
    title: 'Damage',
    body: 'Uploaded satellite scenes are checked for potential damage.',
  },
  {
    verb: 'Prioritize',
    title: 'Priority',
    body: 'Risk and damage combine to rank where help may go first.',
  },
  {
    verb: 'Act',
    title: 'Action',
    body: 'Decision-makers get clear intelligence. People decide.',
  },
]

const MODULES = [
  {
    name: 'Risk Flag',
    stripe: 'var(--color-risk-high)',
    body: 'Uses Open-Meteo weather at the district town coordinate, including temperature, wind, and snow when the forecast returns them, plus NDMA hazard context. An AI model rates each district low, medium, or high. A rule-based scorer takes over if the model is unavailable.',
    to: '/risk-map',
    cta: 'Open Risk Map',
  },
  {
    name: 'Damage Checker',
    stripe: 'var(--color-danger)',
    body: 'Classifies a satellite tile as no, partial or destroyed damage, using a model trained on xBD tiles and Pakistan 2022 flood imagery. It flags images that are not satellite tiles instead of guessing, and Scene mode splits a large image into tiles.',
    to: '/damage-assessment',
    cta: 'Open Damage Assessment',
  },
  {
    name: 'Aid Priority',
    stripe: 'var(--color-risk-low)',
    body: 'Combines each district\u2019s risk score (40%) and damage score (60%) into one ranked list, so the places that need help first rise to the top. The formula is shown on screen, so every rank can be checked.',
    to: '/aid-priority',
    cta: 'Open Aid Priority',
  },
]

const LIMITS = [
  'The damage model is a screening aid, not a building-by-building audit. It is right about two times in three across its three classes, and least reliable on partial damage.',
  'Risk Flag is town-coordinate weather plus an LLM, not a hydrological, glacier, or avalanche model. Snow on high peaks can be understated because the figure is the forecast cell at the town, not the glacier. GLOF, avalanche, and landslide districts still receive live weather inputs when Open-Meteo returns them.',
  'A backtest on the 2022 monsoon showed our rainfall-based scorer flagged only some flood districts as high risk before documented impact. Treat ratings as a starting point.',
  'Nigraan AI supports prioritization. It does not replace emergency responders or official instructions.',
]

function scrollToId(id) {
  const el = document.getElementById(id)
  if (!el) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}

export default function Landing() {
  const [bgIndex, setBgIndex] = useState(0)
  const [fadeIn, setFadeIn] = useState(true)

  useEffect(() => {
    const interval = setInterval(() => {
      setFadeIn(false)
      setTimeout(() => {
        setBgIndex((i) => (i + 1) % BG_IMAGES.length)
        setFadeIn(true)
      }, 800)
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <div className="lp">
      {/* ── Background image carousel ───────────────────────────────── */}
      <div className="lp-bg-stage" aria-hidden="true">
        {BG_IMAGES.map((src, i) => (
          <div
            key={src}
            className="lp-bg-slide"
            style={{
              backgroundImage: `url(${src})`,
              opacity: i === bgIndex ? (fadeIn ? 1 : 0) : 0,
            }}
          />
        ))}
        {/* Gradient overlay: top dark, bottom dark, middle slightly less dark */}
        <div className="lp-bg-overlay" />
      </div>

      <header className="lp-bar">
        <div className="lp-wrap lp-bar-in">
          <button type="button" className="lp-brand" onClick={() => scrollToId('top')}>
            <Logo size="md" />
          </button>
          <nav className="lp-links" aria-label="Page sections">
            {NAV.map(([label, id]) => (
              <button key={id} type="button" className="lp-link" onClick={() => scrollToId(id)}>
                {label}
              </button>
            ))}
          </nav>
          <Link to="/overview" className="btn btn-primary">
            Open console
          </Link>
        </div>
      </header>

      <main id="top" className="lp-content">
        {/* ── Hero: name, slogan, pitch, live-style map ─────────────────── */}
        <section className="lp-hero" aria-labelledby="hero-title">
          <div className="lp-floor" aria-hidden="true" />
          <div className="lp-wrap lp-hero-grid">
            <div>
              <div className="lp-tag lp-tone-critical is-on lp-kicker">
                <i />
                Nigraan AI · Observer · Guardian
              </div>
              <h1 id="hero-title" className="lp-title">
                <span>See the Risk.</span>
                <br />
                <span>Understand the Damage.</span>
                <br />
                <span>Act Faster.</span>
              </h1>
              <p className="lp-lede">
                Nigraan AI transforms disaster data into actionable intelligence — helping identify
                high-risk areas, assess damage, and prioritize humanitarian aid when every minute
                matters.
              </p>
              <div className="lp-actions">
                <Link to="/overview" className="btn btn-primary lp-btn-lg">
                  Explore Disaster Intelligence →
                </Link>
                <button type="button" className="btn lp-btn-lg" onClick={() => scrollToId('how')}>
                  Learn How It Works
                </button>
              </div>
            </div>
            <HeroMap />
          </div>
        </section>

        {/* ── How it works: the slogan as four steps ───────────────────── */}
        <section id="how" className="lp-wrap lp-flow" aria-label="How it works">
          {STEPS.map((step, i) => (
            <div key={step.verb} className="lp-step" style={{ '--i': i }}>
              <small>
                {String(i + 1).padStart(2, '0')} · {step.verb}
              </small>
              <b>{step.title}</b>
              <span>{step.body}</span>
            </div>
          ))}
        </section>

        {/* ── Vision and mission ───────────────────────────────────────── */}
        <section id="vision" className="lp-section">
          <div className="lp-wrap lp-vm">
            <div className="lp-vm-item">
              <h2 className="lp-kicker-h">Our vision</h2>
              <p>
                A Pakistan where no district is caught by surprise. Every flood, landslide and
                drought is seen early, the damage is understood quickly, and aid reaches the
                hardest-hit places first.
              </p>
            </div>
            <div id="mission" className="lp-vm-item">
              <h2 className="lp-kicker-h">Our mission</h2>
              <p>
                To give NDMA and PDMA teams one clear, explainable view of risk, damage and aid
                priority — built on open data, honest about what it can and cannot tell them, and
                always leaving the decision to people.
              </p>
            </div>
          </div>
        </section>

        {/* ── Overview ─────────────────────────────────────────────────── */}
        <section id="overview" className="lp-section">
          <div className="lp-wrap">
            <h2 className="lp-h2">What Nigraan AI does</h2>
            <p className="lp-intro">
              Nigraan AI is a decision-support platform for Pakistan&rsquo;s disaster authorities.
              Three connected modules turn rainfall data and satellite imagery into a ranked list of
              districts, and a console shows how each score was reached.
            </p>

            <div className="lp-modules">
              {MODULES.map((m) => (
                <article
                  key={m.name}
                  className="panel stripe-left lp-module"
                  style={{ '--stripe': m.stripe }}
                >
                  <h3>{m.name}</h3>
                  <p>{m.body}</p>
                  <Link to={m.to} className="btn">
                    {m.cta}
                  </Link>
                </article>
              ))}
            </div>

            <div className="lp-coverage">
              <span>
                Covers {DISTRICTS.length} districts across {HAZARD_TYPES.length} hazard types:
              </span>
              {HAZARD_TYPES.map((hazard) => (
                <HazardIcon key={hazard} hazard={hazard} />
              ))}
            </div>
          </div>
        </section>

        {/* ── Why AI ───────────────────────────────────────────────────── */}
        <section id="why-ai" className="lp-section">
          <div className="lp-wrap lp-why">
            <div>
              <h2 className="lp-h2 lp-sticky">Why we turned to AI</h2>
            </div>
            <div className="lp-prose">
              <p>
                In 2022, floods that began in mid-June killed 1,739 people and affected more than 33
                million, according to NDMA figures (
                <a href={FLOOD_2022_SOURCE.href} target="_blank" rel="noreferrer">
                  {FLOOD_2022_SOURCE.label}
                </a>
                ). Behind those totals sat thousands of separate decisions: which districts to warn,
                which roads and villages were gone, where the next tent, boat or ration should go.
                Each was made with partial information, because the information was scattered:
                forecasts in one place, hazard history in reports, damage in photographs and phone
                calls, needs in spreadsheets.
              </p>
              <p>
                That is where we felt AI could help. Satellite scenes arrive faster than analysts
                can study them by eye, and a model can screen them and tell a person which areas to
                look at first. Rainfall, season and district hazard history are easy to read one at
                a time and hard to weigh together under pressure, and a language model can read them
                side by side and explain a rating in one sentence a duty officer can check. A ranked
                list of aid priorities only helps if it changes when the picture changes, and
                software can re-rank in seconds.
              </p>
              <p>
                It is also where we felt AI should stop. We learned how often these models are
                wrong, so Nigraan AI shows its confidence, flags images that are not satellite tiles
                instead of judging them, shows the formula behind every priority ranking, and leaves
                every decision to people. A tool that is honest about its limits is one responders
                can actually use.
              </p>

              <h3 className="lp-limits-h">What it does not do</h3>
              <ul className="lp-limits">
                {LIMITS.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ── About, contact, resources ────────────────────────────────── */}
        <section className="lp-section">
          <div className="lp-wrap lp-trio">
            <div id="about" className="lp-col">
              <h2 className="lp-h3">About us</h2>
              <p>
                Nigraan AI began as RiskLens, a project for the Bano Qabil × Alibaba Cloud AI
                Hackathon, and grew into a three-module platform for disaster response in Pakistan.
                &ldquo;Nigraan&rdquo; means watcher or guardian: the one who keeps watch so others
                can act.
              </p>
              {SITE.team.length > 0 ? (
                <ul className="lp-team">
                  {SITE.team.map((person) => (
                    <li key={person.name}>
                      <b>{person.name}</b>
                      {person.role ? <span>{person.role}</span> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>

            <div id="contact" className="lp-col">
              <h2 className="lp-h3">Contact</h2>
              <p>Questions, corrections, or interest in a pilot? Reach us here.</p>
              <ul className="lp-links-list">
                <li>
                  <a href={`${SITE.repoUrl}/issues`} target="_blank" rel="noreferrer">
                    Open an issue on GitHub
                  </a>
                </li>
                {SITE.contactEmail ? (
                  <li>
                    <a href={`mailto:${SITE.contactEmail}`}>{SITE.contactEmail}</a>
                  </li>
                ) : null}
              </ul>
            </div>

            <div id="resources" className="lp-col">
              <h2 className="lp-h3">Resources</h2>
              <ul className="lp-links-list">
                {RESOURCES.map((r) => (
                  <li key={r.href}>
                    <a href={r.href} target="_blank" rel="noreferrer">
                      {r.label}
                    </a>
                    <span>{r.note}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      </main>

      <footer className="lp-footer lp-content">
        <div className="lp-wrap">
          <p>
            Nigraan AI is a decision-support system. It supports prioritization and does not replace
            emergency responders or official instructions. Map data on this page is illustrative
            sample data; live assessments are in the console.
          </p>
        </div>
      </footer>
    </div>
  )
}
