<!DOCTYPE html>
<html lang="da">
  <head>
    <meta charset="utf-8" />
    <title>Socialpsykologi Deep Dives – Hold 1 – 2025</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        color-scheme: light dark;
        --bg: #0c1f48;
        --bg-secondary: linear-gradient(140deg, #0c1f48 0%, #143069 45%, #0c1f48 100%);
        --fg: #f2f6ff;
        --muted: #c5d2f5;
        --subtle: rgba(255, 255, 255, 0.12);
        --accent: #7fa8ff;
        --accent-strong: #98bbff;
        --accent-contrast: #08153a;
        --card-bg: rgba(20, 45, 104, 0.82);
        --card-border: rgba(143, 173, 234, 0.25);
        --shadow: 0 22px 42px rgba(4, 10, 28, 0.55);
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        background: var(--bg-secondary);
        color: var(--fg);
        line-height: 1.65;
      }

      main {
        max-width: 960px;
        margin: 0 auto;
        padding: clamp(2.75rem, 6vw, 4.5rem) clamp(1.5rem, 4vw, 3rem) 4.5rem;
      }

      .hero {
        position: relative;
        margin-bottom: clamp(2.75rem, 6vw, 4rem);
        padding: clamp(2.5rem, 5vw, 4rem);
        border-radius: 28px;
        background: linear-gradient(135deg, rgba(26, 57, 120, 0.92), rgba(12, 31, 72, 0.92));
        border: 1px solid rgba(143, 173, 234, 0.26);
        box-shadow: var(--shadow);
        overflow: hidden;
      }

      .hero::after {
        content: "";
        position: absolute;
        inset: -40% 28% 38% -35%;
        background: radial-gradient(circle, rgba(127, 168, 255, 0.28), transparent 60%);
        opacity: 0.85;
        pointer-events: none;
      }

      .hero-content {
        position: relative;
        max-width: 620px;
        z-index: 1;
      }

      .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.45rem 1rem;
        border-radius: 999px;
        background: rgba(127, 168, 255, 0.18);
        color: var(--accent);
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.76rem;
        margin: 0 0 1.1rem;
      }

      h1 {
        font-size: clamp(2.5rem, 5vw, 3.4rem);
        margin: 0 0 1rem;
      }

      p.lead {
        font-size: clamp(1.05rem, 2.2vw, 1.2rem);
        color: rgba(197, 210, 245, 0.82);
        margin-bottom: 1.75rem;
      }

      .cta-group {
        display: flex;
        flex-wrap: wrap;
        gap: 0.85rem;
      }

      .cta {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        padding: 0.7rem 1.5rem;
        border-radius: 14px;
        font-weight: 600;
        text-decoration: none;
        transition: transform 160ms ease, background 160ms ease, box-shadow 160ms ease;
      }

      .cta.primary {
        background: var(--accent);
        color: var(--accent-contrast);
        box-shadow: 0 20px 38px rgba(127, 168, 255, 0.32);
      }

      .cta.primary:hover {
        transform: translateY(-3px);
        background: var(--accent-strong);
      }

      .cta.secondary {
        background: rgba(255, 255, 255, 0.12);
        color: var(--fg);
      }

      .cta.secondary:hover {
        transform: translateY(-3px);
        background: rgba(255, 255, 255, 0.18);
      }

      section {
        margin-top: clamp(3rem, 7vw, 4rem);
      }

      h2 {
        font-size: clamp(1.8rem, 4vw, 2.4rem);
        margin-bottom: 1rem;
      }

      .section-intro {
        max-width: 640px;
        color: rgba(197, 210, 245, 0.82);
        margin-bottom: 2rem;
      }

      .card-grid {
        display: grid;
        gap: 1.6rem;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      }

      .card {
        position: relative;
        padding: 1.9rem;
        border-radius: 22px;
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        backdrop-filter: blur(14px);
        box-shadow: 0 18px 36px rgba(5, 12, 34, 0.34);
        display: flex;
        flex-direction: column;
        gap: 1rem;
        transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
      }

      .card::before {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: inherit;
        border: 1px solid transparent;
        background: linear-gradient(120deg, rgba(127, 168, 255, 0.45), rgba(85, 122, 220, 0.18)) border-box;
        mask: linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0);
        mask-composite: exclude;
        pointer-events: none;
        opacity: 0;
        transition: opacity 160ms ease;
      }

      .card:hover {
        transform: translateY(-6px);
        border-color: rgba(127, 168, 255, 0.55);
        box-shadow: 0 24px 44px rgba(5, 12, 34, 0.46);
      }

      .card:hover::before {
        opacity: 1;
      }

      .card h3 {
        margin: 0;
        font-size: 1.2rem;
      }

      .card p {
        margin: 0;
        color: var(--muted);
      }

      .card-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        margin: -0.6rem 0 0.5rem;
      }

      .card-icon img {
        width: 68px;
        height: 68px;
        filter: drop-shadow(0 20px 32px rgba(127, 168, 255, 0.35));
      }

      .show-card {
        align-items: center;
        text-align: center;
        gap: 1.2rem;
        padding-inline: clamp(1.4rem, 5vw, 2.4rem);
      }

      .show-card h3 {
        font-size: 1.45rem;
      }

      .show-summary {
        margin: 0;
        color: rgba(197, 210, 245, 0.85);
        max-width: 460px;
      }

      .show-links {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 0.8rem;
        margin-top: 0.4rem;
      }

      .show-link {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.65rem 1.4rem;
        border-radius: 999px;
        font-weight: 600;
        text-decoration: none;
        background: rgba(255, 255, 255, 0.12);
        color: var(--fg);
        transition: transform 150ms ease, background 150ms ease, box-shadow 150ms ease;
      }

      .show-link svg {
        width: 18px;
        height: 18px;
      }

      .show-link:hover {
        transform: translateY(-2px);
        background: rgba(255, 255, 255, 0.18);
        box-shadow: 0 16px 28px rgba(6, 14, 34, 0.32);
      }

      .show-link.primary {
        background: var(--accent);
        color: var(--accent-contrast);
        box-shadow: 0 16px 30px rgba(127, 168, 255, 0.28);
      }

      .show-link.primary:hover {
        background: var(--accent-strong);
        box-shadow: 0 20px 36px rgba(127, 168, 255, 0.35);
      }

      .card a {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        color: var(--accent);
        font-weight: 600;
        text-decoration: none;
      }

      .card a svg {
        width: 18px;
        height: 18px;
      }

      .card a:hover {
        text-decoration: underline;
      }

      .upload-card {
        position: relative;
        margin-bottom: 2.6rem;
        padding: clamp(1.8rem, 4vw, 2.6rem);
        border-radius: 26px;
        background: linear-gradient(135deg, rgba(127, 168, 255, 0.2), rgba(34, 64, 134, 0.7));
        border: 1px solid rgba(143, 173, 234, 0.32);
        box-shadow: 0 26px 48px rgba(3, 9, 26, 0.48);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1.6rem;
        overflow: hidden;
      }

      .upload-card::after {
        content: "";
        position: absolute;
        inset: -45% 55% -35% -25%;
        background: radial-gradient(circle, rgba(152, 187, 255, 0.24), transparent 60%);
        opacity: 0.9;
        pointer-events: none;
      }

      .upload-copy {
        position: relative;
        z-index: 1;
        max-width: 540px;
        display: grid;
        gap: 0.9rem;
      }

      .upload-tag {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.3rem 0.85rem;
        border-radius: 999px;
        background: rgba(242, 246, 255, 0.15);
        color: var(--fg);
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-weight: 600;
      }

      .upload-card h3 {
        margin: 0;
        font-size: clamp(1.4rem, 3vw, 1.8rem);
      }

      .upload-card p {
        margin: 0;
        color: rgba(197, 210, 245, 0.85);
      }

      .upload-actions {
        position: relative;
        z-index: 1;
        display: flex;
        align-items: center;
        gap: 1rem;
      }

      .upload-link {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        padding: 0.75rem 1.6rem;
        border-radius: 16px;
        background: var(--fg);
        color: var(--accent-contrast);
        font-weight: 600;
        text-decoration: none;
        box-shadow: 0 18px 34px rgba(15, 35, 80, 0.35);
        transition: transform 160ms ease, box-shadow 160ms ease;
      }

      .upload-link:hover {
        transform: translateY(-3px);
        box-shadow: 0 26px 44px rgba(15, 35, 80, 0.4);
      }

      .upload-link svg {
        width: 18px;
        height: 18px;
      }

      .timeline {
        position: relative;
        padding-left: 1.5rem;
        display: grid;
        gap: 1.8rem;
      }

      .timeline::before {
        content: "";
        position: absolute;
        left: 0.45rem;
        top: 0.4rem;
        bottom: 0.4rem;
        width: 2px;
        background: rgba(152, 187, 255, 0.28);
      }

      .step {
        position: relative;
        padding-left: 1.4rem;
      }

      .step::before {
        content: attr(data-step);
        position: absolute;
        left: -1.55rem;
        top: 0.1rem;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: rgba(127, 168, 255, 0.24);
        color: var(--accent);
        display: grid;
        place-items: center;
        font-weight: 600;
      }

      .step h3 {
        margin: 0 0 0.35rem;
        font-size: 1.05rem;
      }

      .step p {
        margin: 0;
        color: var(--muted);
      }

      .naming ul {
        list-style: none;
        margin: 0.6rem 0 0;
        padding: 0;
        display: grid;
        gap: 0.35rem;
      }

      .naming li {
        background: var(--subtle);
        border-radius: 10px;
        padding: 0.6rem 0.8rem;
      }

      code {
        background: rgba(18, 39, 96, 0.76);
        padding: 0.18rem 0.42rem;
        border-radius: 8px;
        font-size: 0.92rem;
      }

      footer {
        margin-top: clamp(3.5rem, 7vw, 5rem);
        font-size: 0.9rem;
        color: rgba(197, 210, 245, 0.78);
        text-align: center;
      }

      @media (prefers-color-scheme: light) {
        :root {
          --bg: #ecf2ff;
          --bg-secondary: linear-gradient(160deg, #ecf2ff 0%, #dbe7ff 40%, #f4f7ff 100%);
          --fg: #132249;
          --muted: #50618c;
          --subtle: rgba(19, 34, 73, 0.08);
          --accent: #2f5eda;
          --accent-strong: #3f72f0;
          --accent-contrast: #f7f9ff;
          --card-bg: rgba(255, 255, 255, 0.94);
          --card-border: rgba(19, 34, 73, 0.12);
          --shadow: 0 20px 34px rgba(28, 54, 120, 0.16);
        }

        body {
          color: #132249;
        }

        code {
          background: rgba(19, 34, 73, 0.08);
        }

        .hero {
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(223, 233, 255, 0.9));
          border: 1px solid rgba(19, 34, 73, 0.12);
        }

        .hero::after {
          opacity: 0.32;
        }

        .upload-card {
          background: linear-gradient(135deg, rgba(229, 236, 255, 0.95), rgba(196, 212, 255, 0.85));
          border: 1px solid rgba(19, 34, 73, 0.12);
          box-shadow: 0 20px 38px rgba(41, 65, 130, 0.16);
        }

        .upload-tag {
          background: rgba(19, 34, 73, 0.08);
          color: #2f3d68;
        }

        .upload-link {
          background: var(--accent);
          color: var(--accent-contrast);
          box-shadow: 0 16px 30px rgba(47, 94, 218, 0.25);
        }

        .upload-link:hover {
          box-shadow: 0 22px 38px rgba(47, 94, 218, 0.25);
        }

        .show-link {
          background: rgba(47, 94, 218, 0.12);
          color: #1b2b57;
        }

        .show-link:hover {
          background: rgba(47, 94, 218, 0.18);
          box-shadow: 0 12px 24px rgba(31, 62, 140, 0.18);
        }
      }

      @media (max-width: 640px) {
        .hero {
          padding: 2rem;
        }

        .cta {
          width: 100%;
          justify-content: center;
        }

        .upload-card {
          flex-direction: column;
          align-items: flex-start;
          padding: 1.8rem;
        }

        .upload-actions {
          width: 100%;
        }

        .upload-link {
          width: 100%;
          justify-content: center;
        }

        .timeline {
          padding-left: 1rem;
        }
      }
    </style>
  </head>
  <body>
    <main>
      <header class="hero">
        <div class="hero-content">
          <span class="eyebrow">Social Psychology</span>
          <h1>Hold 1s Podcast Hub</h1>
          <p class="lead">
            Lyt til klassens Deep Dives, upload nye episoder på få minutter, og hold styr på ugens
            materiale ét sted. Siden synker direkte med Spotify og vores RSS-feed.
          </p>
          <div class="cta-group">
            <a class="cta primary" href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">Åbn Spotify-serien</a>
            <a class="cta secondary" href="https://drive.google.com/drive/u/7/folders/1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI">Administrer Google Drive</a>
          </div>
        </div>
      </header>

      <section>
        <h2>Socialpsykologi Deep Dives</h2>
        <p class="section-intro">
          Vores første show samler holdets Deep Dives uge for uge. Når der kommer flere serier, får de
          deres egen plads nedenfor, så du tydeligt kan se hvad der er live.
        </p>
        <div class="upload-card">
          <div class="upload-copy">
            <span class="upload-tag">Nyt show?</span>
            <h3>Upload direkte til holdets bibliotek</h3>
            <p>
              Læg lydfiler og assets i Google Drive for at starte en ny serie. Systemet synker automatisk
              med Spotify og RSS, så resten af holdet kan lytte med det samme.
            </p>
          </div>
          <div class="upload-actions">
            <a class="upload-link" href="https://drive.google.com/drive/u/7/folders/1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI">
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M12 5v14m7-7H5"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              Åbn Google Drive
            </a>
          </div>
        </div>
        <div class="card-grid">
          <article class="card show-card">
            <figure class="card-icon">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/1/19/Spotify_logo_without_text.svg"
                alt="Spotify ikon"
                loading="lazy"
              />
            </figure>
            <h3>Hold 1 – 2025: Socialpsykologi Deep Dives</h3>
            <p class="show-summary">
              Dyk ned i ugens pensum, lavet af holdkammeraterne. Vælg mellem fulde episoder eller korte
              briefs, alle synket til Spotify og dit podcast-feed.
            </p>
            <div class="show-links">
              <a class="show-link primary" href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">
                Lyt på Spotify
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path
                    d="M12 5a7 7 0 100 14 7 7 0 000-14z"
                    stroke="currentColor"
                    stroke-width="2"
                  />
                  <path
                    d="M8.5 11.3c2.05-.45 4.38-.2 6.14.55M9 13.7c1.65-.32 3.55-.18 5.08.37M9.4 15.9c1.2-.22 2.5-.13 3.58.26"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                  />
                </svg>
              </a>
              <a class="show-link" href="https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml">
                RSS-feed
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path
                    d="M5 17a1 1 0 112 0 1 1 0 01-2 0z"
                    fill="currentColor"
                  />
                  <path
                    d="M5 8a9 9 0 019 9M5 4a13 13 0 0113 13"
                    stroke="currentColor"
                    stroke-width="2"
                    stroke-linecap="round"
                  />
                </svg>
              </a>
            </div>
          </article>
        </div>
      </section>

      <section>
        <h2>Sådan fungerer systemet</h2>
        <p class="section-intro">
          Uploadprocessen er designet, så alle hurtigt kan bidrage. Følg trinene nedenfor, og episoden er
          live på under en halv time.
        </p>
        <div class="timeline">
          <div class="step" data-step="1">
            <h3>Forbered filen</h3>
            <p>Lav podcasten i NotebookLM eller dit lydværktøj, og eksportér som MP3 eller WAV.</p>
          </div>
          <div class="step" data-step="2">
            <h3>Vælg den rigtige mappe</h3>
            <p>Åbn Drive-mappen, og find undervisningsugen (<code>W4 The Self</code>, <code>W7 Impact</code> osv.).</p>
          </div>
          <div class="step naming" data-step="3">
            <h3>Navngiv korrekt</h3>
            <p>Brug vores fælles format for titler:</p>
            <ul>
              <li>Titelskabelon: <code>W## [Brief] Titel.ext</code></li>
              <li>Brug <code>[Brief]</code> kun til korte sammenfatninger.</li>
              <li><code>Alle kilder</code> dækker hele ugens pensum.</li>
              <li>Eksempler: <code>An integrative theory of intergroup conflict</code>, <code>[Brief] 10. Group behaviour.mp3</code>, <code>Alle kilder.mp3</code></li>
            </ul>
          </div>
          <div class="step" data-step="4">
            <h3>Upload og vent</h3>
            <p>Upload filen til Drive. Efter ~20 minutter vises episoden i Spotify og RSS-feedet.</p>
          </div>
        </div>
      </section>

      <footer>
        Senest opdateret: september 2025 · Spørgsmål? Ping holdet i chatten.
      </footer>
    </main>
  </body>
</html>
