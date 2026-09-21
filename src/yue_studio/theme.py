"""Gradio theme: obsidian studio with frosted glass panels and a lit score desk."""
from __future__ import annotations

import gradio as gr
from gradio.themes.utils import colors, fonts, sizes

# Obsidian backdrop · frosted glass cards · warm score lamp as the focal point.
# obsidian #0b0d14   ink #11141d   glass #1a2030 (60% alpha)
# velvet #2b3148     filament #ff7a45 (warm coral) · ember #ffb86b
# cyan #7dd3fc       mint #5eead4  plum #c084fc  rose #fb7185
# lamp #fff4d8       paper #f6e9c8   ink-note #2a1f12
THEME = gr.themes.Base(
    primary_hue=colors.orange,
    secondary_hue=colors.slate,
    neutral_hue=colors.slate,
    spacing_size=sizes.spacing_md,
    radius_size=sizes.radius_lg,
    text_size=sizes.text_md,
    font=(
        fonts.GoogleFont("Syne"),
        fonts.GoogleFont("Noto Sans SC"),
        "ui-sans-serif",
        "system-ui",
        "sans-serif",
    ),
    font_mono=(
        fonts.GoogleFont("IBM Plex Mono"),
        fonts.GoogleFont("JetBrains Mono"),
        "ui-monospace",
        "Consolas",
        "monospace",
    ),
).set(
    body_background_fill="#0b0d14",
    body_background_fill_dark="#0b0d14",
    body_text_color="#e7eaf3",
    body_text_color_dark="#e7eaf3",
    body_text_color_subdued="#8b94ad",
    body_text_color_subdued_dark="#8b94ad",
    background_fill_primary="#0b0d14",
    background_fill_primary_dark="#0b0d14",
    background_fill_secondary="#11141d",
    background_fill_secondary_dark="#11141d",
    border_color_primary="rgba(255, 255, 255, 0.08)",
    border_color_primary_dark="rgba(255, 255, 255, 0.08)",
    border_color_accent="#ff7a45",
    border_color_accent_dark="#ff7a45",
    color_accent="#ff7a45",
    color_accent_soft="#1a2030",
    color_accent_soft_dark="#1a2030",
    shadow_drop="0 1px 2px rgba(0,0,0,0.4)",
    shadow_drop_lg="0 24px 60px rgba(0,0,0,0.55)",
    block_background_fill="rgba(26, 32, 48, 0.55)",
    block_background_fill_dark="rgba(26, 32, 48, 0.55)",
    block_border_color="rgba(255, 255, 255, 0.07)",
    block_border_color_dark="rgba(255, 255, 255, 0.07)",
    block_border_width="1px",
    block_label_background_fill="transparent",
    block_label_background_fill_dark="transparent",
    block_label_text_color="#c5cee0",
    block_label_text_color_dark="#c5cee0",
    block_label_text_weight="600",
    block_title_text_color="#f1f4fb",
    block_title_text_color_dark="#f1f4fb",
    block_title_text_weight="600",
    block_info_text_color="#8b94ad",
    block_info_text_color_dark="#8b94ad",
    block_shadow="none",
    block_shadow_dark="none",
    panel_background_fill="rgba(26, 32, 48, 0.6)",
    panel_background_fill_dark="rgba(26, 32, 48, 0.6)",
    panel_border_color="rgba(255, 255, 255, 0.07)",
    panel_border_color_dark="rgba(255, 255, 255, 0.07)",
    input_background_fill="rgba(11, 13, 20, 0.55)",
    input_background_fill_dark="rgba(11, 13, 20, 0.55)",
    input_border_color="rgba(255, 255, 255, 0.09)",
    input_border_color_dark="rgba(255, 255, 255, 0.09)",
    input_border_color_focus="#ff7a45",
    input_border_color_focus_dark="#ff7a45",
    input_placeholder_color="#5f6783",
    input_placeholder_color_dark="#5f6783",
    input_shadow_focus="0 0 0 3px rgba(255, 122, 69, 0.18)",
    input_shadow_focus_dark="0 0 0 3px rgba(255, 122, 69, 0.18)",
    button_border_width="0px",
    button_primary_background_fill="#ff7a45",
    button_primary_background_fill_dark="#ff7a45",
    button_primary_background_fill_hover="#ff8c5c",
    button_primary_background_fill_hover_dark="#ff8c5c",
    button_primary_text_color="#1a0e07",
    button_primary_text_color_dark="#1a0e07",
    button_secondary_background_fill="rgba(255, 255, 255, 0.06)",
    button_secondary_background_fill_dark="rgba(255, 255, 255, 0.06)",
    button_secondary_background_fill_hover="rgba(255, 255, 255, 0.12)",
    button_secondary_background_fill_hover_dark="rgba(255, 255, 255, 0.12)",
    button_secondary_text_color="#e7eaf3",
    button_secondary_text_color_dark="#e7eaf3",
    button_cancel_background_fill="rgba(251, 113, 133, 0.18)",
    button_cancel_background_fill_dark="rgba(251, 113, 133, 0.18)",
    button_cancel_text_color="#fda4af",
    button_cancel_text_color_dark="#fda4af",
    checkbox_background_color="rgba(11, 13, 20, 0.6)",
    checkbox_background_color_dark="rgba(11, 13, 20, 0.6)",
    checkbox_background_color_selected="#ff7a45",
    checkbox_background_color_selected_dark="#ff7a45",
    checkbox_border_color="rgba(255, 255, 255, 0.12)",
    checkbox_border_color_dark="rgba(255, 255, 255, 0.12)",
    checkbox_border_color_focus="#ff7a45",
    checkbox_label_background_fill="rgba(26, 32, 48, 0.55)",
    checkbox_label_background_fill_dark="rgba(26, 32, 48, 0.55)",
    checkbox_label_background_fill_selected="rgba(255, 122, 69, 0.16)",
    checkbox_label_background_fill_selected_dark="rgba(255, 122, 69, 0.16)",
    checkbox_label_text_color="#e7eaf3",
    checkbox_label_text_color_dark="#e7eaf3",
    checkbox_label_text_color_selected="#ffd8c2",
    checkbox_label_text_color_selected_dark="#ffd8c2",
    accordion_text_color="#e7eaf3",
    accordion_text_color_dark="#e7eaf3",
    table_border_color="rgba(255, 255, 255, 0.06)",
    table_border_color_dark="rgba(255, 255, 255, 0.06)",
    table_even_background_fill="rgba(255, 255, 255, 0.025)",
    table_even_background_fill_dark="rgba(255, 255, 255, 0.025)",
    table_odd_background_fill="rgba(255, 255, 255, 0.045)",
    table_odd_background_fill_dark="rgba(255, 255, 255, 0.045)",
    table_row_focus="rgba(255, 122, 69, 0.14)",
    table_row_focus_dark="rgba(255, 122, 69, 0.14)",
    table_text_color="#e7eaf3",
    table_text_color_dark="#e7eaf3",
    slider_color="#ff7a45",
    slider_color_dark="#ff7a45",
    stat_background_fill="rgba(26, 32, 48, 0.55)",
    stat_background_fill_dark="rgba(26, 32, 48, 0.55)",
)

FORCE_DARK = """
() => {
  document.documentElement.classList.add("dark");
  document.body.classList.add("dark");
}
"""

CSS = """
@import url("https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700&family=Noto+Sans+SC:wght@400;500;600;700&family=Syne:wght@500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap");

:root {
  --obsidian: #0b0d14;
  --obsidian-2: #11141d;
  --ink: #07090f;
  --glass: rgba(26, 32, 48, 0.55);
  --glass-strong: rgba(26, 32, 48, 0.78);
  --glass-soft: rgba(255, 255, 255, 0.04);
  --glass-edge: rgba(255, 255, 255, 0.09);
  --glass-edge-strong: rgba(255, 255, 255, 0.16);
  --velvet: #2b3148;
  --velvet-2: #1a2030;

  --filament: #ff7a45;
  --filament-dim: #e85a25;
  --ember: #ffb86b;
  --magenta: #fb7185;
  --cyan: #7dd3fc;
  --mint: #5eead4;
  --plum: #c084fc;

  --lamp: #fff4d8;
  --paper: #f6e9c8;
  --paper-line: rgba(40, 30, 12, 0.18);
  --ink-note: #2a1f12;
  --ink-note-soft: #6a5a40;

  --text: #e7eaf3;
  --text-soft: #c5cee0;
  --text-mute: #8b94ad;
  --text-faint: #5f6783;

  --rule: rgba(255, 255, 255, 0.07);
  --rule-strong: rgba(255, 255, 255, 0.14);
  --fail: #fda4af;
  --success: #6ee7b7;

  --radius: 16px;
  --radius-sm: 10px;
  --radius-lg: 22px;
  --shadow-card: 0 1px 0 rgba(255, 255, 255, 0.05) inset,
                 0 20px 50px -20px rgba(0, 0, 0, 0.55);
  --shadow-pop: 0 1px 0 rgba(255, 255, 255, 0.06) inset,
                0 30px 80px -30px rgba(255, 122, 69, 0.35),
                0 8px 30px -10px rgba(0, 0, 0, 0.5);
}

html, body.dark, body {
  background: var(--obsidian) !important;
  color: var(--text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

html, body { text-align: left; }

/* ---------- Backdrop: aurora + grain + soft vignette ---------- */
.gradio-container,
div.gradio-container {
  position: relative !important;
  margin-left: auto !important;
  margin-right: auto !important;
  background:
    radial-gradient(900px 520px at 12% -10%, rgba(192, 132, 252, 0.18), transparent 60%),
    radial-gradient(1100px 620px at 88% 0%, rgba(125, 211, 252, 0.14), transparent 62%),
    radial-gradient(720px 460px at 50% 110%, rgba(255, 122, 69, 0.16), transparent 65%),
    linear-gradient(180deg, #0b0d14 0%, #0a0c12 60%, #07090f 100%) !important;
  color: var(--text) !important;
  font-family: "Noto Sans SC", "Syne", ui-sans-serif, system-ui, sans-serif !important;
  max-width: 1280px !important;
  width: 100% !important;
  padding-top: 1.2rem !important;
  padding-bottom: 3rem !important;
  min-height: 100vh;
}

/* The Gradio wrapper that holds .gradio-container needs to center too. */
body > .gradio-container,
body > div > .gradio-container {
  float: none !important;
}

.gradio-container.fillable {
  max-width: 1280px !important;
}

.gradio-container::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    radial-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 3px 3px;
  opacity: 0.5;
  mix-blend-mode: overlay;
}

.gradio-container > * { position: relative; z-index: 1; }

/* ---------- Reset wrappers that Gradio adds ---------- */
.studio-head-wrap,
.hw-bar-wrap,
.job-progress-wrap {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 !important;
}

/* ---------- Studio head ---------- */
.studio-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.4rem;
  padding: 0.25rem 0.4rem 1.1rem;
  margin-bottom: 0.9rem;
  position: relative;
}

.studio-head::after {
  content: "";
  position: absolute;
  left: 0.4rem; right: 0.4rem; bottom: 0.4rem;
  height: 1px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(255, 122, 69, 0.45) 30%,
    rgba(125, 211, 252, 0.35) 70%,
    transparent 100%);
  opacity: 0.55;
}

.studio-brand {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.studio-seal {
  position: relative;
  flex: none;
  width: 3.1rem;
  height: 3.1rem;
  display: grid;
  place-items: center;
  color: #fff;
  font-family: "Noto Serif SC", "Songti SC", serif;
  font-size: 1.6rem;
  font-weight: 700;
  line-height: 1;
  border-radius: 14px;
  background:
    linear-gradient(135deg, #ff7a45 0%, #fb7185 50%, #c084fc 100%);
  box-shadow:
    0 10px 30px -10px rgba(255, 122, 69, 0.7),
    inset 0 1px 0 rgba(255, 255, 255, 0.4),
    inset 0 -1px 0 rgba(0, 0, 0, 0.2);
}

.studio-seal::after {
  content: "";
  position: absolute;
  inset: -3px;
  border-radius: 17px;
  background: linear-gradient(135deg, rgba(255, 122, 69, 0.5), rgba(192, 132, 252, 0.4));
  filter: blur(14px);
  opacity: 0.55;
  z-index: -1;
}

.studio-head h1 {
  font-family: "Syne", "Noto Sans SC", sans-serif;
  font-weight: 800;
  font-size: 1.85rem;
  letter-spacing: 0.005em;
  margin: 0;
  color: var(--text);
  line-height: 1.05;
  background: linear-gradient(90deg, #fff 0%, #ffd8c2 50%, #c084fc 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.studio-head p {
  color: var(--text-mute);
  margin: 0.25rem 0 0;
  font-size: 0.78rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 500;
}

.studio-tags {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.studio-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.75rem;
  font-size: 0.7rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--text-soft);
  background: var(--glass);
  border: 1px solid var(--glass-edge);
  border-radius: 999px;
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
}

.studio-tag .dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--filament);
  box-shadow: 0 0 8px var(--filament);
}

.studio-tag.cool .dot { background: var(--cyan); box-shadow: 0 0 8px var(--cyan); }
.studio-tag.warm .dot { background: var(--ember); box-shadow: 0 0 8px var(--ember); }

/* ---------- Hardware bar ---------- */
.hw-bar-wrap { margin: 0 0 0.7rem; }

.hw-bar {
  display: grid;
  grid-template-columns: minmax(220px, 1.1fr) minmax(260px, 1.4fr) minmax(180px, 1fr);
  gap: 0.85rem 1.2rem;
  align-items: center;
  padding: 0.85rem 1.05rem;
  border-radius: var(--radius);
  background:
    linear-gradient(135deg, rgba(255, 122, 69, 0.06) 0%, transparent 40%),
    var(--glass);
  border: 1px solid var(--glass-edge);
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
  position: relative;
  overflow: hidden;
}

.hw-bar::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), transparent 30%);
  pointer-events: none;
}

.hw-vram {
  display: flex;
  align-items: center;
  gap: 0.7rem;
  flex-wrap: wrap;
  min-width: 0;
}

.hw-k {
  color: var(--text-mute);
  font-size: 0.65rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  font-weight: 600;
}

.hw-v {
  font-family: "Syne", "Noto Sans SC", sans-serif;
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text);
  letter-spacing: 0.005em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  background: linear-gradient(90deg, #fff 0%, #ffd8c2 60%, #ffb86b 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.hw-leds {
  display: inline-flex;
  gap: 4px;
  margin-left: 0.2rem;
  align-items: flex-end;
}

.hw-leds i {
  display: block;
  width: 5px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.08);
  transition: all 0.25s ease;
}

.hw-leds i:nth-child(1) { height: 9px; }
.hw-leds i:nth-child(2) { height: 12px; }
.hw-leds i:nth-child(3) { height: 15px; }
.hw-leds i:nth-child(4) { height: 18px; }
.hw-leds i:nth-child(5) { height: 21px; }
.hw-leds i:nth-child(6) { height: 24px; }

.hw-leds i.on {
  background: linear-gradient(180deg, #ffb86b 0%, #ff7a45 100%);
  box-shadow: 0 0 12px rgba(255, 122, 69, 0.6);
}

.hw-gpu {
  color: var(--text-soft);
  font-size: 0.78rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hw-params {
  margin: 0;
  color: var(--text-soft);
  font-size: 0.78rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  letter-spacing: 0.02em;
  padding: 0.55rem 0.75rem;
  border-radius: var(--radius-sm);
  background: rgba(11, 13, 20, 0.45);
  border: 1px solid var(--glass-edge);
  font-variant-numeric: tabular-nums;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hw-note {
  margin: 0;
  color: var(--text-mute);
  font-size: 0.76rem;
  line-height: 1.4;
  min-width: 0;
}

.hw-note.warn { color: var(--fail); }

.hw-controls {
  margin: 0 0 0.55rem;
  padding: 0.9rem 1rem;
  border-radius: var(--radius);
  background: var(--glass);
  border: 1px solid var(--glass-edge);
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
}

.hw-params-panel { margin-bottom: 0.65rem; }

/* ---------- Tabs ---------- */
.studio-tabs { margin-top: 0.4rem; }

.tab-nav, .tab-container, .tab-wrapper {
  background: transparent !important;
  border: 0 !important;
  gap: 0.3rem !important;
}

.tab-nav button, .tab-container button, button[role="tab"] {
  background: rgba(255, 255, 255, 0.04) !important;
  color: var(--text-mute) !important;
  border: 1px solid transparent !important;
  border-radius: 999px !important;
  box-shadow: none !important;
  font-family: "Noto Sans SC", "Syne", sans-serif !important;
  font-weight: 600 !important;
  letter-spacing: 0.06em;
  padding: 0.55rem 1.1rem !important;
  transition: all 0.2s ease !important;
}

.tab-nav button:hover, .tab-container button:hover, button[role="tab"]:hover {
  color: var(--text) !important;
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: var(--glass-edge) !important;
}

.tab-nav button.selected, .tab-container button.selected, button[role="tab"][aria-selected="true"] {
  color: #1a0e07 !important;
  background: linear-gradient(135deg, #ffb86b 0%, #ff7a45 100%) !important;
  box-shadow: 0 6px 18px -6px rgba(255, 122, 69, 0.65) !important;
  border-color: transparent !important;
}

/* ---------- The lit score desk: warm focal point ---------- */
.staff-panel,
.gradio-container .block.staff-panel {
  background:
    radial-gradient(800px 240px at 50% -40%, rgba(255, 244, 216, 0.6), transparent 65%),
    linear-gradient(180deg, #fff4d8 0%, #f6e9c8 100%) !important;
  color: var(--ink-note) !important;
  border: 1px solid rgba(120, 90, 30, 0.22) !important;
  border-radius: var(--radius) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    0 24px 60px -20px rgba(0, 0, 0, 0.55),
    0 0 80px -20px rgba(255, 184, 107, 0.4);
  overflow: hidden !important;
  position: relative;
  padding: 0 !important;
  margin: 0 !important;
}

/* Gradio HTML wraps the iframe in .wrap / padded chrome — strip it so
   the parchment card and the score are one surface, not nested boxes. */
.staff-panel > .wrap,
.staff-panel .wrap,
.staff-panel .html-container,
.staff-panel .prose {
  padding: 0 !important;
  margin: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  overflow: hidden;
}

.staff-panel iframe,
.score-frame {
  width: 100%;
  height: 480px;
  border: 0 !important;
  outline: none;
  background: transparent;
  display: block;
  border-radius: 0;
  margin: 0;
  box-shadow: none;
}

.score-empty, .score-error {
  position: relative;
  background:
    repeating-linear-gradient(
      to bottom,
      transparent 0 21px,
      var(--paper-line) 21px 22px
    ),
    linear-gradient(180deg, #fff4d8 0%, #f6e9c8 100%);
  color: var(--ink-note-soft);
  padding: 2.4rem 1.4rem 1.6rem;
  min-height: 10rem;
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.88rem;
  text-align: center;
}

.score-empty span, .score-error p {
  position: relative;
  color: var(--ink-note-soft);
  font-weight: 500;
}

.score-error pre {
  white-space: pre-wrap;
  margin: 0.7rem 0 0;
  text-align: left;
}

/* ---------- Buttons ---------- */
button.primary, .primary {
  background: linear-gradient(135deg, #ffb86b 0%, #ff7a45 100%) !important;
  color: #1a0e07 !important;
  border: none !important;
  font-weight: 700 !important;
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.35) inset,
    0 -1px 0 rgba(0, 0, 0, 0.15) inset,
    0 8px 24px -8px rgba(255, 122, 69, 0.55) !important;
  letter-spacing: 0.02em;
  transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}

button.primary:hover, .primary:hover {
  background: linear-gradient(135deg, #ffc285 0%, #ff8c5c 100%) !important;
  transform: translateY(-1px);
  box-shadow:
    0 1px 0 rgba(255, 255, 255, 0.4) inset,
    0 -1px 0 rgba(0, 0, 0, 0.15) inset,
    0 12px 28px -8px rgba(255, 122, 69, 0.7) !important;
}

button.primary:active, .primary:active {
  transform: translateY(0);
}

button.secondary, .lgb .secondary {
  background: rgba(255, 255, 255, 0.06) !important;
  color: var(--text) !important;
  border: 1px solid var(--glass-edge) !important;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  font-weight: 600 !important;
}

button.secondary:hover, .lgb .secondary:hover {
  background: rgba(255, 255, 255, 0.12) !important;
  border-color: var(--glass-edge-strong) !important;
}

footer { display: none !important; }

/* ---------- Inputs & textareas ---------- */
#env-box textarea, #env-box input,
.invoke-log textarea,
textarea, input[type="text"], input[type="number"] {
  font-family: "IBM Plex Mono", ui-monospace, monospace !important;
  font-size: 0.82rem !important;
  line-height: 1.55 !important;
}

.gradio-container textarea,
.gradio-container input[type="text"],
.gradio-container input[type="number"] {
  background: rgba(11, 13, 20, 0.55) !important;
  border: 1px solid var(--glass-edge) !important;
  border-radius: var(--radius-sm) !important;
  color: var(--text) !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease !important;
}

.gradio-container textarea:focus,
.gradio-container input[type="text"]:focus,
.gradio-container input[type="number"]:focus {
  background: rgba(11, 13, 20, 0.75) !important;
  border-color: rgba(255, 122, 69, 0.6) !important;
  box-shadow: 0 0 0 3px rgba(255, 122, 69, 0.18) !important;
}

/* ---------- Cards: rounded glass ---------- */
.gradio-container .block {
  border-radius: var(--radius) !important;
  background: var(--glass) !important;
  border: 1px solid var(--glass-edge) !important;
  box-shadow: var(--shadow-card) !important;
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
}

.gradio-container .label-wrap span {
  font-weight: 600;
  letter-spacing: 0.04em;
  font-size: 0.78rem;
  text-transform: uppercase;
  color: var(--text-soft);
}

.gradio-container table.table {
  font-size: 0.84rem;
  background: transparent !important;
}

.gradio-container table.table th {
  background: rgba(255, 255, 255, 0.04) !important;
  color: var(--text-soft) !important;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 0.72rem;
  border-bottom: 1px solid var(--rule-strong) !important;
}

.gradio-container table.table td {
  border-bottom: 1px solid var(--rule) !important;
}

.gradio-container .accordion > .label-wrap {
  background: var(--glass) !important;
  border: 1px solid var(--glass-edge) !important;
  border-radius: var(--radius) !important;
  padding: 0.7rem 0.95rem !important;
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
}

/* ---------- Radio / checkbox ---------- */
.gradio-container .radio,
.gradio-container .checkbox {
  background: transparent !important;
}

.gradio-container .radio label,
.gradio-container .checkbox label {
  background: rgba(255, 255, 255, 0.04) !important;
  border: 1px solid var(--glass-edge) !important;
  border-radius: 999px !important;
  color: var(--text-soft) !important;
  padding: 0.4rem 0.85rem !important;
  margin: 0 0.3rem 0.3rem 0 !important;
  transition: all 0.15s ease !important;
  font-size: 0.82rem !important;
  font-weight: 500 !important;
}

.gradio-container .radio label:hover,
.gradio-container .checkbox label:hover {
  background: rgba(255, 255, 255, 0.08) !important;
  border-color: var(--glass-edge-strong) !important;
  color: var(--text) !important;
}

.gradio-container .radio input:checked + label,
.gradio-container .checkbox input:checked + label {
  background: rgba(255, 122, 69, 0.18) !important;
  border-color: rgba(255, 122, 69, 0.5) !important;
  color: var(--text) !important;
  box-shadow: 0 0 0 1px rgba(255, 122, 69, 0.3) inset;
}

/* ---------- Dropdown ---------- */
.gradio-container .dropdown {
  background: rgba(11, 13, 20, 0.55) !important;
  border: 1px solid var(--glass-edge) !important;
  border-radius: var(--radius-sm) !important;
}

/* ---------- Progress: glass strip with glow ---------- */
.job-progress-wrap { margin: 0 0 0.6rem; }

.job-progress {
  background: var(--glass) !important;
  border: 1px solid var(--glass-edge) !important;
  border-radius: var(--radius) !important;
  padding: 0.8rem 1rem !important;
  backdrop-filter: blur(20px) saturate(140%);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  box-shadow: var(--shadow-card) !important;
  position: relative;
  overflow: hidden;
}

.job-progress-label {
  color: var(--text);
  font-size: 0.82rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.job-progress-label::before {
  content: "";
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--filament);
  box-shadow: 0 0 8px var(--filament);
  animation: job-pulse 1.6s ease-in-out infinite;
}

.job-progress.idle .job-progress-label,
.job-progress.done .job-progress-label { color: var(--text-mute); }
.job-progress.idle .job-progress-label::before,
.job-progress.done .job-progress-label::before { animation: none; opacity: 0.5; }

.job-progress.done .job-progress-label::before { background: var(--success); box-shadow: 0 0 8px var(--success); }

.job-progress.failed .job-progress-label { color: var(--fail); }
.job-progress.failed .job-progress-label::before { background: var(--fail); box-shadow: 0 0 8px var(--fail); animation: none; }

.job-progress-track {
  position: relative;
  height: 6px;
  background: rgba(11, 13, 20, 0.6);
  border: 1px solid var(--glass-edge);
  border-radius: 99px;
  overflow: hidden;
}

.job-progress-bar {
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, #ffb86b 0%, #ff7a45 100%);
  box-shadow: 0 0 12px rgba(255, 122, 69, 0.55);
  transition: width 0.2s ease;
  position: relative;
}

.job-progress-bar::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
  animation: job-shimmer 1.8s linear infinite;
}

.job-progress-bar.indeterminate {
  width: 30%;
  animation: job-progress-slide 1.4s ease-in-out infinite;
}

.job-progress-bar.indeterminate::after { animation: none; }

@keyframes job-progress-slide {
  0% { transform: translateX(-120%); }
  100% { transform: translateX(420%); }
}

@keyframes job-shimmer {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(200%); }
}

@keyframes job-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}

/* ---------- Audio player chrome ---------- */
.gradio-container audio {
  border-radius: var(--radius-sm) !important;
  background: rgba(11, 13, 20, 0.55) !important;
  border: 1px solid var(--glass-edge) !important;
  padding: 0.4rem !important;
}

/* ---------- Focus visibility ---------- */
.gradio-container input:focus-visible,
.gradio-container textarea:focus-visible,
.gradio-container button:focus-visible,
.gradio-container select:focus-visible {
  outline: 2px solid var(--filament);
  outline-offset: 2px;
}

/* ---------- Selection ---------- */
::selection {
  background: rgba(255, 122, 69, 0.35);
  color: #fff;
}

/* ---------- Custom scrollbar ---------- */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 99px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
::-webkit-scrollbar-thumb:hover { background: rgba(255, 255, 255, 0.18); background-clip: padding-box; }

/* ---------- Responsive ---------- */
@media (max-width: 820px) {
  .studio-head h1 { font-size: 1.45rem; }
  .studio-tags { display: none; }
  .score-frame { height: 360px; }
  .hw-bar {
    grid-template-columns: 1fr;
    padding: 0.7rem 0.85rem;
  }
  .hw-params { white-space: normal; }
}

@media (prefers-reduced-motion: reduce) {
  .job-progress-bar.indeterminate { animation: none; width: 40%; }
  .job-progress-bar::after { animation: none; }
  .job-progress-label::before { animation: none; }
  .hw-leds i.on { box-shadow: none; }
  button.primary:hover, .primary:hover { transform: none; }
}
"""
