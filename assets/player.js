/* One audio element for the whole page. The waveform is the scrubber.
   Release assets are served without CORS headers, so everything here works from
   the media element's own clock — never WebAudio, which would mute the element. */

(() => {
  const audio = new Audio();
  audio.preload = "none";
  let active = null;                       // the .wave bound to the audio element

  const motionOK = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = document.documentElement;

  const fmt = (s) => {
    if (!isFinite(s)) return "--:--";
    return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  };

  const hostOf = (wave) => wave.closest(".card, .player, .row, .hero");

  /* ---------------------------------------------------------- waveform SVG */

  // Cards ship their bars as numbers (62 inline SVGs would cost a megabyte)
  const buildWave = (wave) => {
    if (wave.querySelector("svg") || !wave.dataset.peaks) return;
    const peaks = wave.dataset.peaks.split(",").map(Number);
    const slot = 100 / peaks.length;
    const w = slot * 0.62;
    const bars = peaks.map((p, i) => {
      const h = Math.max(2, p);
      return `<rect x="${(i * slot + (slot - w) / 2).toFixed(3)}" y="${((100 - h) / 2).toFixed(2)}" ` +
             `width="${w.toFixed(3)}" height="${h.toFixed(2)}" rx="${(w / 2).toFixed(3)}"/>`;
    }).join("");
    wave.innerHTML =
      `<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">` +
      `<g class="bars">${bars}</g><g class="played">${bars}</g></svg>`;
    if (motionOK) {
      wave.querySelectorAll("svg g rect").forEach((bar, i) => {
        bar.style.animationDelay = (i * 2) + "ms";
      });
    }
  };

  /* ---------------------------------------------------------- mini player */

  const mini = document.createElement("div");
  mini.className = "mini";
  mini.hidden = true;
  mini.innerHTML =
    `<button class="play mini-play" aria-pressed="false" aria-label="Play or pause">
       <svg class="play-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>
       <svg class="pause-icon" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5h4v13H3zM9 1.5h4v13H9z"/></svg>
     </button>
     <img alt="" hidden>
     <p class="mini-title"></p>
     <span class="timecode mini-time">0:00</span>
     <span class="mini-bar"><i></i></span>`;
  document.body.appendChild(mini);

  const miniImg = mini.querySelector("img");
  const miniTitle = mini.querySelector(".mini-title");
  const miniTime = mini.querySelector(".mini-time");

  const fillMini = (wave) => {
    const host = hostOf(wave);
    if (!host) return;
    const titleEl = host.querySelector(".title a, h2 a, h1");
    miniTitle.textContent = titleEl ? titleEl.textContent.trim() : "";
    const img = host.querySelector("img");
    if (img) {
      miniImg.src = img.currentSrc || img.src;
      miniImg.hidden = false;
    } else {
      miniImg.hidden = true;
    }
    mini.style.setProperty("--accent", wave.dataset.accent || "");
  };

  const showMini = (show) => {
    if (show && mini.hidden) {
      mini.hidden = false;
      requestAnimationFrame(() => mini.classList.add("shown"));
    } else if (!show) {
      mini.classList.remove("shown");
    }
  };

  /* ---------------------------------------------------------- painting */

  // Transcript cues, sorted by start time, for the "currently speaking" highlight
  const cues = [...document.querySelectorAll(".t-cue")];
  const cueTimes = cues.map((c) => Number(c.dataset.t));
  let currentCue = -1;

  const markCue = (t) => {
    if (!cues.length) return;
    let lo = 0, hi = cueTimes.length - 1, found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (cueTimes[mid] <= t) { found = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    if (found === currentCue) return;
    cues[currentCue]?.parentElement.classList.remove("is-current");
    cues[found]?.parentElement.classList.add("is-current");
    currentCue = found;
  };

  const paint = () => {
    if (!active) return;
    const total = audio.duration || Number(active.dataset.duration) || 0;
    const pct = total ? Math.min(100, (audio.currentTime / total) * 100) : 0;
    active.style.setProperty("--progress", pct + "%");
    active.setAttribute("aria-valuenow", Math.round(audio.currentTime));
    mini.style.setProperty("--progress", pct + "%");
    miniTime.textContent = fmt(audio.currentTime);
    const now = hostOf(active)?.querySelector(".now");
    if (now) now.textContent = fmt(audio.currentTime);
    markCue(audio.currentTime);
  };

  const setState = (wave, playing) => {
    const host = hostOf(wave);
    host?.querySelector(".play")?.setAttribute("aria-pressed", String(playing));
    mini.querySelector(".mini-play").setAttribute("aria-pressed", String(playing));
    wave.classList.toggle("is-playing", playing);
    host?.classList.toggle("is-playing", playing);
  };

  const bind = (wave) => {
    if (active === wave) return;
    if (active) {
      setState(active, false);
      active.style.setProperty("--progress", "0%");
      hostOf(active)?.classList.remove("is-active", "is-playing");
    }
    active = wave;
    buildWave(wave);
    hostOf(wave)?.classList.add("is-active");
    root.style.setProperty("--accent", wave.dataset.accent || "");
    fillMini(wave);
    audio.src = wave.dataset.src;
    audio.preload = "metadata";
  };

  // Assigning currentTime before metadata arrives is discarded; hold it
  const seekTo = (seconds) => {
    if (audio.readyState >= 1) {
      audio.currentTime = seconds;
      paint();
      return;
    }
    audio.addEventListener("loadedmetadata", function once() {
      audio.removeEventListener("loadedmetadata", once);
      audio.currentTime = seconds;
      paint();
    });
  };

  const toggle = (wave) => {
    if (active !== wave) {
      bind(wave);
      audio.play();
      return;
    }
    audio.paused ? audio.play() : audio.pause();
  };

  const seek = (wave, clientX) => {
    const r = wave.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    if (active !== wave) bind(wave);
    seekTo(ratio * (audio.duration || Number(wave.dataset.duration) || 0));
    if (audio.paused) audio.play();
  };

  /* ---------------------------------------------------------- audio events */

  audio.addEventListener("timeupdate", paint);
  audio.addEventListener("play", () => { if (active) { setState(active, true); showMini(true); } });
  audio.addEventListener("pause", () => active && setState(active, false));
  audio.addEventListener("ended", () => {
    if (!active) return;
    setState(active, false);
    active.style.setProperty("--progress", "0%");
  });

  // Release URLs redirect to a signed URL that expires after about an hour.
  // If playback dies on a stale one, re-request and carry on from the same spot.
  audio.addEventListener("error", () => {
    if (!active || !audio.src) return;
    const at = audio.currentTime;
    const src = active.dataset.src;
    audio.src = src + (src.includes("?") ? "&" : "?") + "r=" + Date.now();
    audio.addEventListener("loadedmetadata", function once() {
      audio.removeEventListener("loadedmetadata", once);
      audio.currentTime = at;
      audio.play();
    });
  });

  /* ---------------------------------------------------------- interaction */

  document.addEventListener("click", (e) => {
    // Transcript timestamps drive the episode player
    const cue = e.target.closest(".t-cue");
    if (cue) {
      e.preventDefault();
      const wave = document.querySelector(".player .wave");
      if (wave) {
        if (active !== wave) bind(wave);
        seekTo(Number(cue.dataset.t));
        audio.play();
      }
      return;
    }
    if (e.target.closest(".mini-play")) {
      if (active) toggle(active);
      return;
    }
    const btn = e.target.closest(".play");
    if (btn) {
      e.preventDefault();
      const wave = hostOf(btn)?.querySelector(".wave");
      if (wave) toggle(wave);
      return;
    }
    const wave = e.target.closest(".wave");
    if (wave) {
      e.preventDefault();
      seek(wave, e.clientX);
      return;
    }
    // Hand the clicked cover to the next page's view transition
    const link = e.target.closest(".card .title a");
    if (link) {
      const img = link.closest(".card")?.querySelector(".cover");
      if (img) img.style.viewTransitionName = "cover";
    }
  });

  window.addEventListener("pageshow", () => {
    document.querySelectorAll(".card .cover").forEach((i) => (i.style.viewTransitionName = ""));
  });

  document.addEventListener("keydown", (e) => {
    const wave = e.target.closest?.(".wave");
    if (!wave) return;
    const total = audio.duration || Number(wave.dataset.duration) || 0;
    const step = e.shiftKey ? 60 : 15;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      if (active !== wave) bind(wave);
      seekTo(Math.max(0, Math.min(total,
        audio.currentTime + (e.key === "ArrowRight" ? step : -step))));
    } else if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      toggle(wave);
    }
  });

  /* ---------------------------------------------------------- entrances */

  const reveals = document.querySelectorAll(".reveal");

  if (!motionOK || !("IntersectionObserver" in window)) {
    reveals.forEach((el) => el.classList.add("shown"));
  } else {
    let seen = 0;
    const io = new IntersectionObserver((entries) => {
      entries.filter((en) => en.isIntersecting).forEach((en, i) => {
        en.target.style.transitionDelay = Math.min(i * 45, 320) + "ms";
        en.target.classList.add("shown");
        io.unobserve(en.target);
        seen++;
      });
    }, { rootMargin: "0px 0px -6% 0px" });
    reveals.forEach((el) => io.observe(el));
  }

  // Draw the server-rendered waveforms (hero, episode page) with a stagger
  document.querySelectorAll(".wave svg").forEach((svg) => {
    if (!motionOK) return;
    svg.querySelectorAll("g rect").forEach((bar, i) => {
      bar.style.animationDelay = (i * 2) + "ms";
    });
  });

  // The mini player appears once the main player has scrolled away
  const anchor = document.querySelector(".hero, .player");
  if (anchor && "IntersectionObserver" in window) {
    new IntersectionObserver(([entry]) => {
      showMini(!entry.isIntersecting && active !== null);
    }, { threshold: 0 }).observe(anchor);
  }
})();
