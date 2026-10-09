/* One audio element for the whole page. The waveform is the scrubber.
   Note: release assets are served without CORS headers, so everything here works
   from the media element's own clock — never WebAudio, which would mute it. */

(() => {
  const audio = new Audio();
  audio.preload = "none";
  let active = null; // the .wave currently bound to the audio element

  const fmt = (s) => {
    if (!isFinite(s)) return "--:--";
    const m = Math.floor(s / 60);
    return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  };

  const paint = () => {
    if (!active) return;
    const total = audio.duration || Number(active.dataset.duration) || 0;
    const pct = total ? Math.min(100, (audio.currentTime / total) * 100) : 0;
    active.style.setProperty("--progress", pct + "%");
    active.setAttribute("aria-valuenow", Math.round(audio.currentTime));
    const now = active.closest(".player, .row, .hero")?.querySelector(".now");
    if (now) now.textContent = fmt(audio.currentTime);
  };

  const setButton = (wave, playing) => {
    const btn = wave.closest(".player, .row, .hero")?.querySelector(".play");
    if (btn) btn.setAttribute("aria-pressed", String(playing));
    wave.classList.toggle("is-playing", playing);
  };

  const bind = (wave) => {
    if (active === wave) return;
    if (active) {
      setButton(active, false);
      active.style.setProperty("--progress", "0%");
    }
    active = wave;
    audio.src = wave.dataset.src;
    audio.preload = "metadata";
  };

  const toggle = (wave) => {
    if (active !== wave) {
      bind(wave);
      audio.play();
      return;
    }
    audio.paused ? audio.play() : audio.pause();
  };

  // Setting currentTime before metadata arrives is discarded, so hold it until ready
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

  const seek = (wave, clientX) => {
    const r = wave.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    if (active !== wave) bind(wave);
    const total = audio.duration || Number(wave.dataset.duration) || 0;
    seekTo(ratio * total);
    if (audio.paused) audio.play();
  };

  audio.addEventListener("timeupdate", paint);
  audio.addEventListener("play", () => active && setButton(active, true));
  audio.addEventListener("pause", () => active && setButton(active, false));
  audio.addEventListener("ended", () => {
    if (!active) return;
    setButton(active, false);
    active.style.setProperty("--progress", "0%");
  });

  // Release-asset URLs redirect to a signed URL that expires after about an hour.
  // If playback dies on a stale one, re-request and carry on from the same spot.
  audio.addEventListener("error", () => {
    if (!active || !audio.src) return;
    const at = audio.currentTime;
    audio.src = active.dataset.src + (active.dataset.src.includes("?") ? "&" : "?") + "r=" + Date.now();
    audio.addEventListener("loadedmetadata", function once() {
      audio.removeEventListener("loadedmetadata", once);
      audio.currentTime = at;
      audio.play();
    });
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".play");
    if (btn) {
      const wave = btn.closest(".player, .row, .hero")?.querySelector(".wave");
      if (wave) toggle(wave);
      return;
    }
    const wave = e.target.closest(".wave");
    if (wave) seek(wave, e.clientX);
  });

  // Keyboard: the waveform is a slider
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

  // Entrances: reveal each group as it arrives, staggering the bars inside it
  const motionOK = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const targets = document.querySelectorAll(".reveal");

  if (!motionOK || !("IntersectionObserver" in window)) {
    targets.forEach((el) => el.classList.add("shown"));
  } else {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("shown");
        entry.target.querySelectorAll(".wave svg g rect").forEach((bar, i) => {
          bar.style.animationDelay = (i * 1.6) + "ms";
        });
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px" });
    targets.forEach((el) => io.observe(el));
  }

  // The page tints itself with whatever episode is playing
  const root = document.documentElement;
  const tint = (wave) => {
    const accent = wave?.dataset.accent;
    if (accent) root.style.setProperty("--accent", accent);
  };
  document.addEventListener("click", (e) => {
    const host = e.target.closest(".row, .hero, .player");
    if (host) tint(host.querySelector(".wave"));
  });
})();
