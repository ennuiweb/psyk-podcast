<!DOCTYPE html>
<html lang="da">
  <head>
    <meta charset="utf-8" />
    <title>Socialpsykologi Deep Dives – Hold 1 – 2025</title>
    <style>
      :root {
        color-scheme: light dark;
        --bg: #0a0d12;
        --fg: #f5f7fa;
        --muted: #c4c9d4;
        --accent: #1db954;
        --card-bg: rgba(255, 255, 255, 0.04);
        --card-border: rgba(255, 255, 255, 0.08);
        font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
      }

      body {
        margin: 0;
        background: var(--bg);
        color: var(--fg);
        line-height: 1.6;
      }

      main {
        max-width: 960px;
        margin: 0 auto;
        padding: 3rem 1.75rem 4rem;
      }

      h1 {
        font-size: clamp(2.2rem, 4vw, 3rem);
        margin: 0 0 0.5rem;
      }

      p.lead {
        font-size: 1.1rem;
        color: var(--muted);
        margin-top: 0;
      }

      section {
        margin-top: 3rem;
      }

      section:first-of-type {
        margin-top: 2.5rem;
      }

      h2 {
        font-size: clamp(1.6rem, 3vw, 2.2rem);
        margin-bottom: 1rem;
      }

      .card-grid {
        display: grid;
        gap: 1.25rem;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        margin-bottom: 2rem;
      }

      .card {
        display: flex;
        flex-direction: column;
        gap: 0.75rem;
        padding: 1.5rem;
        background: var(--card-bg);
        border: 1px solid var(--card-border);
        border-radius: 16px;
        transition: transform 150ms ease, border-color 150ms ease;
      }

      .card:hover {
        transform: translateY(-4px);
        border-color: rgba(29, 185, 84, 0.45);
      }

      .card h3 {
        margin: 0;
        font-size: 1.15rem;
      }

      .card a {
        color: var(--accent);
        font-weight: 600;
        text-decoration: none;
      }

      .card a:hover {
        text-decoration: underline;
      }

      .spotify-icon {
        display: flex;
        justify-content: center;
        margin: 1.5rem 0;
      }

      .spotify-icon img {
        width: min(200px, 50vw);
        height: auto;
      }

      ol, ul {
        padding-left: 1.5rem;
      }

      code {
        background: rgba(255, 255, 255, 0.08);
        padding: 0.15rem 0.35rem;
        border-radius: 6px;
        font-size: 0.95rem;
      }

      footer {
        margin-top: 3rem;
        font-size: 0.9rem;
        color: var(--muted);
      }

      @media (prefers-color-scheme: light) {
        :root {
          --bg: #f8fafc;
          --fg: #0f172a;
          --muted: #4f5b76;
          --card-bg: #ffffff;
          --card-border: rgba(15, 23, 42, 0.08);
        }

        code {
          background: rgba(15, 23, 42, 0.06);
        }
      }
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Socialpsykologi Deep Dives – Hold 1 – 2025</h1>
        <p class="lead">
          Velkommen til vores fælles bibliotek med socialpsykologi-podcasts. Her finder du alt, du
          behøver for at lytte, bidrage med nye episoder og forstå, hvordan systemet hænger sammen.
        </p>
      </header>

      <section>
        <h2>Lyt med det samme</h2>
        <div class="card-grid">
          <article class="card">
            <h3>Google Drive</h3>
            <p>Hele arkivet med Deep Dives, sorteret efter undervisningsuge.</p>
            <a href="https://drive.google.com/drive/u/7/folders/1uPt6bHjivcD9z-Tw6Q2xbIld3bmH_WyI">Åbn mappen</a>
          </article>
          <article class="card">
            <h3>Spotify-serien</h3>
            <p>Følg med i de seneste uploads direkte i din podcast-app.</p>
            <a href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">Lyt på Spotify</a>
          </article>
          <article class="card">
            <h3>RSS-feed</h3>
            <p>Tilføj feedet i enhver podcast-app, der understøtter RSS.</p>
            <a href="https://raw.githubusercontent.com/ennuiweb/psyk-podcast/main/shows/social-psychology/feeds/rss.xml">Hent RSS-feedet</a>
          </article>
        </div>

        <div class="spotify-icon">
          <a href="https://open.spotify.com/show/08cv2AZyBv2W9S8GiAysVP">
            <img
              src="https://upload.wikimedia.org/wikipedia/commons/1/19/Spotify_logo_without_text.svg"
              alt="Spotify ikon"
              loading="lazy"
            />
          </a>
        </div>
      </section>

      <section>
        <h2>Sådan fungerer systemet</h2>
        <ol>
          <li>Hver undervisningsuge har sin egen mappe i Google Drive (fx <code>W4 The Self</code>).</li>
          <li>
            Lav din podcast i NotebookLM, download lydfilen, og læg den i den mappe, der matcher ugen.
          </li>
          <li>
            Lyt i Google Drive, Spotify eller en anden podcast-app. Nye uploads tager ca. 20 minutter at
            dukke op i feedet.
          </li>
        </ol>
      </section>

      <section>
        <h2>How to Upload</h2>
        <ol>
          <li><strong>Lav din lydfil.</strong> Eksportér fra NotebookLM eller dit foretrukne værktøj.</li>
          <li><strong>Vælg den rigtige uge-mappe.</strong> Match undervisningsplanens uge og emne.</li>
          <li>
            <strong>Navngiv filen korrekt.</strong>
            <ul>
              <li>Skabelon: <code>W## [Brief] Titel.ext</code></li>
              <li>Brug <code>[Brief]</code> kun til brief-versioner.</li>
              <li>Brug <code>Alle kilder</code> hvis episoden dækker alle ugens kilder.</li>
              <li>Ellers genbrug navnet på hovedkilden (bogkapitel, artikel osv.).</li>
              <li>Eksempler: <code>An integrative theory of intergroup conflict</code>, <code>[Brief] 10. Group behaviour.mp3</code>, <code>Alle kilder.mp3</code></li>
            </ul>
          </li>
          <li><strong>Upload til Drive.</strong> Træk filen over i den relevante ugemappe.</li>
        </ol>
      </section>

      <footer>
        Senest opdateret: september 2025. Spørgsmål? Ping os på holdets chat.
      </footer>
    </main>
  </body>
</html>
