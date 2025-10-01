<html lang="da">
  <head>
    <meta charset="utf-8" />
    <title>Socialpsykologi Deep Dives – Hold 1 – 2025</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {
        color-scheme: light dark;
        --bg: #080b12;
        --bg-secondary: radial-gradient(circle at 20% 20%, rgba(29, 185, 84, 0.2), transparent 42%),
          radial-gradient(circle at 80% -10%, rgba(94, 234, 212, 0.18), transparent 36%),
          #080b12;
        --fg: #f5f7fa;
        --muted: #c4c9d4;
        --subtle: rgba(255, 255, 255, 0.08);
        --accent: #1db954;
        --accent-strong: #1ed760;
        --card-bg: rgba(10, 15, 25, 0.72);
        --card-border: rgba(255, 255, 255, 0.12);
        --shadow: 0 18px 42px rgba(5, 10, 20, 0.4);
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
        background: linear-gradient(135deg, rgba(12, 20, 35, 0.75), rgba(12, 20, 35, 0.6));
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: var(--shadow);
        overflow: hidden;
      }

      .hero::after {
        content: "";
        position: absolute;
        inset: -40% 30% 35% -35%;
        background: radial-gradient(circle, rgba(29, 185, 84, 0.25), transparent 55%);
        opacity: 0.8;
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
        padding: 0.4rem 0.9rem;
        border-radius: 999px;
        background: rgba(29, 185, 84, 0.12);
        color: var(--accent);
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.76rem;
        margin: 0 0 1rem;
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

      .hero-highlights {
        display: grid;
        gap: 0.85rem;
        margin: 0 0 2rem;
        padding: 0;
        list-style: none;
      }

      .hero-highlights li {
        display: flex;
        align-items: center;
        gap: 0.75rem;
      }

      .hero-highlights svg {
        width: 20px;
        height: 20px;
        flex: 0 0 20px;
      }

      .cta-group {
        display: flex;
        flex-wrap: wrap;
        gap: 0.85rem;
      }

      .cta {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.7rem 1.4rem;
        border-radius: 12px;
        font-weight: 600;
        text-decoration: none;
        transition: transform 160ms ease, background 160ms ease, box-shadow 160ms ease;
      }

      .cta.primary {
        background: var(--accent);
        color: #04110a;
        box-shadow: 0 18px 36px rgba(29, 185, 84, 0.3);
      }

      .cta.primary:hover {
        transform: translateY(-3px);
        background: var(--accent-strong);
      }

      .cta.secondary {
        background: rgba(255, 255, 255, 0.08);
        color: var(--fg);
      }

      .cta.secondary:hover {
        transform: translateY(-3px);
        background: rgba(255, 255, 255, 0.12);
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

      .card-grid {
        display: grid;
        gap: 1.4rem;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      }

      .card {
        position: relative;
        padding: 1.7rem;
        border-radius: 20px;
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        backdrop-filter: blur(12px);
        box-shadow: 0 12px 24px rgba(5, 10, 20, 0.28);
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        transition: transform 160ms ease, border-color 160ms ease;
      }

      .card::before {
        content: "";
        position: absolute;
        inset: 0;
        border-radius: inherit;
        border: 1px solid transparent;
        background: linear-gradient(120deg, rgba(29, 185, 84, 0.35), rgba(66, 226, 183, 0.1)) border-box;
        mask: linear-gradient(#fff 0 0) padding-box, linear-gradient(#fff 0 0);
        mask-composite: exclude;
        pointer-events: none;
        opacity: 0;
        transition: opacity 160ms ease;
      }

      .card:hover {
        transform: translateY(-6px);
        border-color: rgba(29, 185, 84, 0.45);
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
        justify-content: flex-start;
        margin: -0.25rem 0 0.4rem;
      }

      .card-icon img {
        width: 50px;
        height: 50px;
        filter: drop-shadow(0 16px 28px rgba(29, 185, 84, 0.32));
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
        background: rgba(255, 255, 255, 0.14);
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
        background: rgba(29, 185, 84, 0.22);
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
        background: rgba(255, 255, 255, 0.06);
        border-radius: 10px;
        padding: 0.6rem 0.8rem;
      }

      code {
        background: rgba(12, 20, 35, 0.55);
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

      @media (prefers-color-scheme: light) {
        :root {
          --bg: #f8fafc;
          --bg-secondary: radial-gradient(circle at -8% -10%, rgba(94, 234, 212, 0.22), transparent 45%),
            radial-gradient(circle at 82% 12%, rgba(29, 185, 84, 0.18), transparent 50%),
            #f8fafc;
          --fg: #0f172a;
          --muted: #4f5b76;
          --card-bg: rgba(255, 255, 255, 0.84);
          --card-border: rgba(15, 23, 42, 0.1);
          --shadow: 0 18px 32px rgba(15, 23, 42, 0.18);
        }

        code {
          background: rgba(15, 23, 42, 0.08);
        }

        .hero {
          background: linear-gradient(135deg, rgba(241, 245, 249, 0.86), rgba(255, 255, 255, 0.72));
          border: 1px solid rgba(15, 23, 42, 0.08);
        }

        .hero::after {
          opacity: 0.45;
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
          <h1>Hold 1 – 2025 Podcast Hub</h1>
          <p class="lead">
            Lyt til klassens Deep Dives, upload nye episoder på få minutter, og hold styr på ugens
            materiale ét sted. Siden synker direkte med Spotify og vores RSS-feed.
          </p>
          <div class="cta-group">
            <a class="cta primary" href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">Åbn Spotify-serien</a>
            <a class="cta secondary" href="https://drive.google.com/drive/u/7/folders/1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI">Gå til Google Drive</a>
          </div>
        </div>
      </header>

      <section>
        <h2>Lyt med det samme</h2>
        <p class="section-intro">
          Vælg din favoritplatform. Alle links peger direkte på klassens egen samling af episoder, så du
          kan lytte med det samme – uanset om du bruger Spotify, en RSS-læser eller Google Drive.
        </p>
        <div class="card-grid">
          <article class="card">
            <h3>Google Drive-bibliotek</h3>
            <p>Filer sorteret efter undervisningsuge, klar til download eller streaming.</p>
            <a href="https://drive.google.com/drive/u/7/folders/1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI">
              Åbn mappen
              <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path
                  d="M5 12h14M13 6l6 6-6 6"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </a>
          </article>
          <article class="card">
            <figure class="card-icon">
              <img
                src="https://upload.wikimedia.org/wikipedia/commons/1/19/Spotify_logo_without_text.svg"
                alt="Spotify ikon"
                loading="lazy"
              />
            </figure>
            <h3>Spotify-serien</h3>
            <p>Lyt hvor som helst. Serien opdateres automatisk, når nye episoder uploades.</p>
            <a href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">
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
          </article>
          <article class="card">
            <h3>RSS-feed</h3>
            <p>Tilføj feedet manuelt i Apple Podcasts eller valgfri RSS-app.</p>
            <a href="https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml">
              Hent RSS-feedet
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
              <li>Titelskabelon: <code> [Brief] Titel.ext</code></li>
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
    </main>
  </body>
</html>
