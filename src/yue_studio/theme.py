"""Gradio theme tokens: ink scoreboard chrome, staff-paper work surface."""

CSS = """
@import url("https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=IBM+Plex+Mono:wght@400;500&display=swap");

:root {
  --ink: #0e0c0a;
  --ink-panel: #161310;
  --paper: #efe6d4;
  --paper-line: rgba(40, 32, 24, 0.16);
  --brass: #c4a35a;
  --brass-dim: #8d7340;
  --mute: #8a8073;
  --rule: #2a241c;
}

html, body, .gradio-container {
  background: var(--ink) !important;
  color: #e8dfd0 !important;
  font-family: "IBM Plex Mono", ui-monospace, monospace !important;
}

.gradio-container {
  max-width: 1180px !important;
}

.studio-head {
  position: relative;
  padding: 1.4rem 0.4rem 1.1rem;
  border-bottom: 1px solid var(--rule);
  margin-bottom: 0.8rem;
}

.studio-head::before {
  content: "";
  position: absolute;
  inset: 0.85rem 0 auto 0;
  height: 42px;
  background: repeating-linear-gradient(
    to bottom,
    transparent 0 7px,
    var(--paper-line) 7px 8px
  );
  opacity: 0.35;
  pointer-events: none;
}

.studio-head h1 {
  font-family: "Cormorant Garamond", Georgia, serif;
  font-weight: 600;
  font-size: 2.35rem;
  letter-spacing: 0.04em;
  margin: 0;
  color: var(--paper);
}

.studio-head p {
  color: var(--mute);
  margin: 0.35rem 0 0;
  font-size: 0.82rem;
}

.hw-bar-wrap {
  margin: 0.1rem 0 0.55rem;
}

.hw-bar {
  background: var(--ink-panel);
  border: 1px solid var(--rule);
  padding: 0.7rem 0.95rem 0.8rem;
}

.hw-vram {
  display: flex;
  align-items: baseline;
  gap: 0.7rem;
  flex-wrap: wrap;
}

.hw-k {
  color: var(--mute);
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.hw-v {
  font-family: "Cormorant Garamond", Georgia, serif;
  font-size: 2.05rem;
  color: var(--paper);
  letter-spacing: 0.02em;
  line-height: 1;
}

.hw-gpu {
  color: var(--brass);
  font-size: 0.82rem;
}

.hw-params {
  margin: 0.4rem 0 0;
  color: var(--paper);
  font-size: 0.78rem;
}

.hw-note {
  margin: 0.18rem 0 0;
  color: var(--mute);
  font-size: 0.75rem;
}

.hw-controls {
  margin: 0 0 0.25rem;
}

.hw-params-panel {
  margin-bottom: 0.7rem;
}

.staff-panel {
  background: var(--paper) !important;
  color: #1c1610 !important;
  border: 1px solid #cbbd9e !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.35);
}

.score-frame {
  width: 100%;
  height: 480px;
  border: 0;
  background: #efe6d4;
}

.score-empty, .score-error {
  background: #efe6d4;
  color: #1c1610;
  padding: 1rem 1.1rem;
  min-height: 8rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.85rem;
}

.score-error pre {
  white-space: pre-wrap;
}

button.primary, .primary {
  background: var(--brass) !important;
  color: #1a140c !important;
  border: none !important;
}

footer { display: none !important; }

#env-box textarea, #env-box input {
  font-size: 0.78rem !important;
}

.invoke-log textarea {
  font-size: 0.75rem !important;
  line-height: 1.35 !important;
}

.job-progress-wrap {
  margin: 0 0 0.55rem;
}

.job-progress {
  background: var(--ink-panel);
  border: 1px solid var(--rule);
  padding: 0.7rem 0.85rem;
}

.job-progress-label {
  color: var(--paper);
  font-size: 0.78rem;
  margin-bottom: 0.45rem;
}

.job-progress.idle .job-progress-label,
.job-progress.done .job-progress-label {
  color: var(--mute);
}

.job-progress.failed .job-progress-label {
  color: #d4a08a;
}

.job-progress-track {
  position: relative;
  height: 8px;
  background: #2a241c;
  border-radius: 99px;
  overflow: hidden;
}

.job-progress-bar {
  height: 100%;
  width: 0;
  background: var(--brass);
  transition: width 0.15s linear;
}

.job-progress-bar.indeterminate {
  width: 28%;
  animation: job-progress-slide 1.15s ease-in-out infinite;
}

@keyframes job-progress-slide {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(420%); }
}
"""
