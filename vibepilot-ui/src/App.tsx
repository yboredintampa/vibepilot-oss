import React, { useEffect, useState } from "react";
import "./App.css";

type Theme = "dark" | "soft";

const App: React.FC = () => {
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "dark" ? "soft" : "dark"));
  };

  const themeLabel = theme === "dark" ? "Soft light" : "Dark mode";

  return (
    <div className={`app app--${theme}`}>
      <header className="nav">
        <div className="container nav__inner">
          <div className="nav__brand">
            VIBE<span>PILOT</span>
          </div>
          <nav className="nav__links">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
          </nav>
          <div className="nav__actions">
            <button className="nav__theme" type="button" onClick={toggleTheme}>
              {themeLabel}
            </button>
            <a href="#request" className="nav__cta">
              Request early access
            </a>
          </div>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="hero">
          <div className="container hero__grid">
            <div className="hero__copy">
              <p className="eyebrow">Built for owners, not agencies.</p>
              <h1>Let an AI pilot your brand&apos;s vibe.</h1>
              <p className="hero__subtitle">
                VibePilot watches your content, tests new posts, and learns what
                actually works. It&apos;s your always-on social media co-pilot
                for local businesses and niche brands.
              </p>

              <div className="hero__actions">
                <a href="#request" className="btn btn--primary">
                  Get on the launch list
                </a>
                <a href="#sample" className="btn btn--ghost">
                  Watch a sample posting run
                </a>
              </div>

              <div className="hero__pills">
                <span className="pill">Fully customizable posting schedule</span>
                <span className="pill">Weekly long-form blogs available</span>
                <span className="pill">Multi-platform ready</span>
                <span className="pill pill--accent">Privacy-first</span>
              </div>

              <p className="hero__privacy">
                Your content, audiences, and performance data stay yours.
                VibePilot doesn&apos;t resell, rent, or train external models on
                your business data.
              </p>
            </div>

            <aside
              className="hero__card"
              aria-label="Today's autopilot summary"
            >
              <h2>Today&apos;s autopilot summary</h2>
              <div className="summary__stats">
                <div className="summary__stat">
                  <span className="summary__label">Posts scheduled</span>
                  <span className="summary__value">3</span>
                </div>
                <div className="summary__stat">
                  <span className="summary__label">Accounts watched</span>
                  <span className="summary__value">4</span>
                </div>
                <div className="summary__stat">
                  <span className="summary__label">Engagement lift</span>
                  <span className="summary__value">+38%</span>
                </div>
              </div>
              <ul className="summary__list">
                <li>
                  <span className="dot dot--green" />
                  Next post at 10:15 AM – “Before/after spotlight”
                </li>
                <li>
                  <span className="dot dot--blue" />
                  Best performer: “Sunday myth-busting thread”
                </li>
                <li>
                  <span className="dot dot--orange" />
                  Suggestion: Add 1 more vertical video this week
                </li>
              </ul>
            </aside>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="section">
          <div className="container">
            <h2>How VibePilot works</h2>
            <div className="cards cards--three">
              <div className="card">
                <h3>1. Connect your pages</h3>
                <p>
                  Link Facebook, Instagram, and other platforms you want on
                  autopilot. You stay in control with approvals and guardrails.
                </p>
              </div>
              <div className="card">
                <h3>2. Set your &quot;vibe&quot;</h3>
                <p>
                  Choose your tone, posting pace, and what you never want
                  posted. VibePilot learns from your brand and past content.
                </p>
              </div>
              <div className="card">
                <h3>3. Let it test &amp; learn</h3>
                <p>
                  The agent experiments with timing, formats, and hooks, then
                  shows you what&apos;s actually moving the needle.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="section section--alt">
          <div className="container">
            <h2>Built for owners, not agencies.</h2>
            <div className="cards cards--three">
              <div className="card">
                <h3>Daily posting engine</h3>
                <p>
                  A fully customizable posting schedule: once a week, once a
                  day, or multiple times per day. VibePilot adapts to your
                  bandwidth and goals instead of forcing a fixed 3×-per-day
                  plan.
                </p>
              </div>
              <div className="card">
                <h3>Guardrails you control</h3>
                <p>
                  Lock in brand rules, banned phrases, and hard no-go zones.
                  VibePilot stays on-brand, even when it&apos;s experimenting.
                </p>
              </div>
              <div className="card">
                <h3>Privacy-first by design</h3>
                <p>
                  Your performance data, audiences, and content history never
                  become someone else&apos;s training set. Your data powers your
                  results, not a giant ad network.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Pricing teaser */}
        <section id="pricing" className="section">
          <div className="container">
            <h2>Pricing built for small teams</h2>
            <div className="cards">
              <div className="card card--highlight">
                <h3>Autopilot co-pilot</h3>
                <p className="card__price">Coming soon</p>
                <ul className="card__list">
                  <li>Custom posting schedule per channel</li>
                  <li>3x weekly long-form blog option</li>
                  <li>Multi-platform support as you grow</li>
                  <li>Owner-friendly analytics &amp; insights</li>
                </ul>
                <a href="#request" className="btn btn--primary btn--full">
                  Get early access pricing
                </a>
              </div>
            </div>
          </div>
        </section>

        {/* Request section */}
        <section id="request" className="section section--alt">
          <div className="container">
            <h2>Get on the launch list</h2>
            <p className="section__subtitle">
              Be first in line when VibePilot opens for a small group of
              early-access businesses.
            </p>
            <form className="simple-form">
              <input
                type="email"
                placeholder="you@example.com"
                aria-label="Email address"
              />
              <button type="submit" className="btn btn--primary">
                Request early access
              </button>
            </form>
            <p className="form__note">
              No spam. No list rental. Just launch updates and a look behind the
              curtain.
            </p>
          </div>
        </section>

        <footer className="footer">
          <div className="container footer__inner">
            <span>© {new Date().getFullYear()} VibePilot</span>
            <span className="footer__note">
              Built for local businesses that want compounding, not chaos.
            </span>
          </div>
        </footer>
      </main>
    </div>
  );
};

export default App;
