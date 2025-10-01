<html lang="da">
  <head>
    <meta charset="utf-8" />
    <title>Socialpsykologi Deep Dives – Hold 1 – 2025</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        color-scheme: light;
        --bg: #ffffff;
        --bg-secondary: linear-gradient(140deg, #ffffff 0%, #f2f5ff 45%, #ffffff 100%);
        --fg: #16213d;
        --muted: #5d6d92;
        --subtle: rgba(22, 33, 61, 0.08);
        --accent: #2f5eda;
        --accent-strong: #244bd3;
        --accent-contrast: #ffffff;
        --card-bg: #ffffff;
        --card-border: rgba(22, 33, 61, 0.1);
        --shadow: 0 20px 38px rgba(22, 33, 61, 0.12);
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
      }

      * {
        box-sizing: border-box;
      }

      body {
        margin: 0;
        min-height: 100vh;
        background: var(--bg);
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
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(234, 240, 255, 0.92));
        border: 1px solid rgba(47, 94, 218, 0.14);
        box-shadow: var(--shadow);
        overflow: hidden;
      }

      .hero::after {
        content: "";
        position: absolute;
        inset: -45% 30% 40% -30%;
        background: radial-gradient(circle, rgba(47, 94, 218, 0.16), transparent 60%);
        opacity: 0.9;
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
        color: var(--muted);
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
        box-shadow: 0 20px 38px rgba(47, 94, 218, 0.25);
      }

      .cta.primary:hover {
        transform: translateY(-3px);
        background: var(--accent-strong);
      }

      .cta.secondary {
        background: var(--subtle);
        color: var(--fg);
      }

      .cta.secondary:hover {
        transform: translateY(-3px);
        background: rgba(47, 94, 218, 0.12);
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
        color: var(--muted);
        margin-bottom: 2rem;
      }

      .deep-dive-section {
        margin-bottom: clamp(3.4rem, 7vw, 4.8rem);
        display: flex;
        justify-content: center;
      }

      .deep-dive-card {
        width: min(100%, 720px);
        padding: clamp(2.6rem, 6vw, 3.6rem);
        border-radius: 28px;
        background: linear-gradient(160deg, rgba(247, 249, 255, 0.98), rgba(231, 237, 255, 0.94));
        border: 1px solid rgba(47, 94, 218, 0.16);
        box-shadow: 0 26px 52px rgba(22, 33, 61, 0.14);
        display: grid;
        gap: clamp(1.6rem, 3vw, 2.2rem);
      }

      .card-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.4rem 1rem;
        border-radius: 999px;
        background: rgba(127, 168, 255, 0.18);
        color: var(--accent);
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        font-size: 0.78rem;
      }

      .deep-dive-card h2 {
        margin: 0;
        font-size: clamp(2rem, 4.2vw, 2.6rem);
      }

      .card-intro {
        margin: 0;
        max-width: 560px;
        color: var(--muted);
      }

      .drive-feature {
        position: relative;
        display: flex;
        align-items: center;
        gap: clamp(1.3rem, 3vw, 2rem);
        padding: clamp(1.8rem, 3.6vw, 2.4rem);
        border-radius: 24px;
        background: linear-gradient(155deg, rgba(47, 94, 218, 0.12), rgba(152, 176, 255, 0.18));
        border: 1px solid rgba(47, 94, 218, 0.2);
        box-shadow: 0 22px 40px rgba(22, 33, 61, 0.12);
        overflow: hidden;
      }

      .drive-feature::after {
        content: "";
        position: absolute;
        inset: -45% 52% -36% -30%;
        background: radial-gradient(circle, rgba(47, 94, 218, 0.16), transparent 65%);
        opacity: 0.7;
        pointer-events: none;
      }

      .drive-copy {
        position: relative;
        z-index: 1;
        display: grid;
        gap: 0.9rem;
        max-width: 460px;
      }

      .drive-copy h3 {
        margin: 0;
        font-size: clamp(1.4rem, 3.1vw, 1.85rem);
      }

      .drive-copy p {
        margin: 0;
        color: var(--muted);
      }

      .drive-button {
        position: relative;
        z-index: 1;
        display: inline-flex;
        align-items: center;
        gap: 0.6rem;
        padding: 0.85rem 1.9rem;
        border-radius: 16px;
        background: var(--accent);
        color: var(--accent-contrast);
        font-weight: 600;
        text-decoration: none;
        box-shadow: 0 20px 36px rgba(47, 94, 218, 0.25);
        transition: transform 160ms ease, box-shadow 160ms ease, background 160ms ease;
      }

      .drive-button:hover {
        transform: translateY(-3px);
        background: var(--accent-strong);
        box-shadow: 0 26px 48px rgba(47, 94, 218, 0.28);
      }

      .drive-button svg {
        width: 18px;
        height: 18px;
      }

      .series-feature {
        display: flex;
        align-items: center;
        gap: clamp(1.2rem, 2.8vw, 1.8rem);
      }

      .series-icon {
        width: 64px;
        height: 64px;
        border-radius: 18px;
        background: rgba(30, 215, 96, 0.15);
        display: grid;
        place-items: center;
      }

      .series-icon img {
        width: 36px;
        height: 36px;
      }

      .series-copy h3 {
        margin: 0 0 0.6rem;
        font-size: clamp(1.3rem, 2.8vw, 1.7rem);
      }

      .series-copy p {
        margin: 0;
        color: var(--muted);
      }

      .series-actions {
        display: flex;
        flex-wrap: wrap;
        gap: 0.8rem;
      }

      .series-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.55rem;
        min-width: 164px;
        padding: 0.75rem 1.6rem;
        border-radius: 14px;
        background: rgba(22, 33, 61, 0.08);
        color: var(--fg);
        font-weight: 600;
        text-decoration: none;
        transition: transform 160ms ease, background 160ms ease, box-shadow 160ms ease;
      }

      .series-button svg {
        width: 18px;
        height: 18px;
      }

      .series-button:hover {
        transform: translateY(-2px);
        background: rgba(47, 94, 218, 0.12);
        box-shadow: 0 16px 28px rgba(22, 33, 61, 0.12);
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
        background: rgba(47, 94, 218, 0.2);
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
        background: rgba(47, 94, 218, 0.18);
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
        background: var(--subtle);
        padding: 0.18rem 0.42rem;
        border-radius: 8px;
        font-size: 0.92rem;
      }

      footer {
        margin-top: clamp(3.5rem, 7vw, 5rem);
        font-size: 0.9rem;
        color: var(--muted);
        text-align: center;
      }

      @media (max-width: 640px) {
        .hero {
          padding: 2rem;
        }

        .cta {
          width: 100%;
          justify-content: center;
        }

        .deep-dive-card {
          padding: 2.2rem;
        }

        .drive-feature {
          flex-direction: column;
          align-items: flex-start;
          padding: 1.8rem;
        }

        .drive-button {
          width: 100%;
          justify-content: center;
        }

        .series-feature {
          flex-direction: column;
          align-items: flex-start;
        }

        .series-icon {
          width: 56px;
          height: 56px;
        }

        .series-actions {
          flex-direction: column;
        }

        .series-button {
          width: 100%;
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

      <section class="deep-dive-section">
        <div class="deep-dive-card">
          <span class="card-eyebrow">Nyt show?</span>
          <h2>Socialpsykologi Deep Dives</h2>
          <p class="card-intro">
            Vores første show samler holdets Deep Dives uge for uge. Når der kommer flere serier, får de
            deres egen plads nedenfor, så du tydeligt kan se hvad der er live.
          </p>

          <div class="drive-feature">
            <div class="drive-copy">
              <h3>Upload direkte til holdets bibliotek</h3>
              <p>
                Læg lydfiler og assets i Google Drive for at starte en ny serie. Systemet synker automatisk
                med Spotify og RSS, så resten af holdet kan lytte med det samme.
              </p>
            </div>
            <a class="drive-button" href="https://drive.google.com/drive/u/7/folders/1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI">
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

          <div class="series-feature">
            <figure class="series-icon">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/1/19/Spotify_logo_without_text.svg"
                alt="Spotify ikon"
                loading="lazy"
              />
            </figure>
            <div class="series-copy">
              <h3>Hold 1 – 2025: Socialpsykologi Deep Dives</h3>
              <p>
                Dyk ned i ugens pensum, lavet af holdkammeraterne. Vælg mellem fulde episoder eller korte
                briefs, alle synket til Spotify og dit podcast-feed.
              </p>
            </div>
          </div>

          <div class="series-actions">
            <a class="series-button" href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">
              Lyt på Spotify
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 5a7 7 0 100 14 7 7 0 000-14z" stroke="currentColor" stroke-width="2" />
                <path
                  d="M8.5 11.3c2.05-.45 4.38-.2 6.14.55M9 13.7c1.65-.32 3.55-.18 5.08.37M9.4 15.9c1.2-.22 2.5-.13 3.58.26"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                />
              </svg>
            </a>
            <a class="series-button" href="https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml">
              RSS-feed
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 17a1 1 0 112 0 1 1 0 01-2 0z" fill="currentColor" />
                <path d="M5 8a9 9 0 019 9M5 4a13 13 0 0113 13" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
              </svg>
            </a>
          </div>
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
