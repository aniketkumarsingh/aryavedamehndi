/*
 * Image Studio web client - drop into any website.
 *
 *   <script type="module" src="https://YOUR-STUDIO-HOST/widget/image-studio.js"></script>
 *   <image-studio endpoint="https://YOUR-STUDIO-HOST" preset="studio-warm" target="#photo"></image-studio>
 *   <input type="file" id="photo" name="photo" hidden>   <!-- optional: receives the enhanced file -->
 *
 * Attributes
 *   endpoint  base URL of the Image Studio API (default: the script's own origin)
 *   preset    preset name; omit to let the user pick from the server's presets
 *   presets   comma-separated list to limit the picker
 *   target    CSS selector of an <input type=file>; "Use this photo" puts the result there
 *   format    jpeg | webp | png (default: the preset's)
 *   api-key   sent as X-API-Key (only use keys meant to be public, e.g. origin-restricted)
 *
 * Events (bubble, composed)
 *   image-studio:result  detail { file, blob, report, width, height }
 *   image-studio:use     detail { file, report } - after "Use this photo"
 *   image-studio:error   detail { error }
 *
 * Theme with CSS variables on the element:
 *   --is-accent, --is-accent-text, --is-surface, --is-text, --is-muted, --is-border, --is-radius, --is-font
 *
 * Or use the client directly:
 *   import { ImageStudioClient } from ".../widget/image-studio.js";
 *   const r = await new ImageStudioClient({ endpoint }).process(file, { preset: "product-white" });
 */

const SCRIPT_ORIGIN = (() => {
  try {
    return new URL(import.meta.url).origin;
  } catch {
    return location.origin;
  }
})();

export class ImageStudioClient {
  constructor({ endpoint = SCRIPT_ORIGIN, apiKey = null } = {}) {
    this.endpoint = endpoint.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  _headers() {
    return this.apiKey ? { "X-API-Key": this.apiKey } : {};
  }

  async _check(res) {
    if (res.ok) return res;
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  async presets() {
    const res = await fetch(`${this.endpoint}/v1/presets`, { headers: this._headers() });
    return (await this._check(res)).json();
  }

  async analyze(file, { preset = "default" } = {}) {
    const body = new FormData();
    body.append("file", file);
    body.append("preset", preset);
    const res = await fetch(`${this.endpoint}/v1/analyze`, { method: "POST", body, headers: this._headers() });
    return (await this._check(res)).json();
  }

  /** Returns { blob, file, report, width, height }. */
  async process(file, { preset = "default", options = null, format = null, width = null, height = null, signal } = {}) {
    const body = new FormData();
    body.append("file", file);
    body.append("preset", preset);
    if (options) body.append("options", JSON.stringify(options));
    const q = new URLSearchParams({ response: "json" });
    if (format) q.set("format", format);
    if (width) q.set("width", width);
    if (height) q.set("height", height);
    const res = await fetch(`${this.endpoint}/v1/process?${q}`, { method: "POST", body, headers: this._headers(), signal });
    const data = await (await this._check(res)).json();
    const blob = await (await fetch(data.image)).blob();
    const ext = { "image/jpeg": "jpg", "image/webp": "webp", "image/png": "png" }[blob.type] || "jpg";
    const base = (file.name || "photo").replace(/\.[^.]+$/, "");
    const out = new File([blob], `${base}-enhanced.${ext}`, { type: blob.type });
    return { blob, file: out, report: data.report, width: data.width, height: data.height };
  }
}

const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const LABELS = {
  low_resolution: "Low resolution",
  blurry: "Out of focus",
  underexposed: "Too dark",
  overexposed: "Too bright",
  color_cast: "Colour cast",
  busy_background: "Busy background",
  small_subject: "Subject too small",
  noisy: "Noisy",
  no_subject: "No clear subject",
  upscaled: "Enlarged from a small photo",
};

const STYLE = `
:host { display:block; font-family:var(--is-font, system-ui, sans-serif); color:var(--is-text,#1f1a17);
  --_accent:var(--is-accent,#5C1A21); --_accent-text:var(--is-accent-text,#fff); --_surface:var(--is-surface,#fff);
  --_muted:var(--is-muted,#6b625b); --_border:var(--is-border,#e3d9cc); --_radius:var(--is-radius,12px); }
* { box-sizing:border-box; }
.box { background:var(--_surface); border:1px solid var(--_border); border-radius:var(--_radius); padding:16px; }
.drop { display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; min-height:180px;
  border:2px dashed var(--_border); border-radius:calc(var(--_radius) - 4px); cursor:pointer; text-align:center; padding:16px; }
.drop:hover, .drop.over, .drop:focus-within { border-color:var(--_accent); }
.drop strong { font-size:1rem; } .drop span { color:var(--_muted); font-size:.875rem; }
input[type=file] { position:absolute; width:1px; height:1px; opacity:0; }
.row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-top:12px; }
select, button, a.btn { font:inherit; font-size:.9rem; border-radius:8px; padding:8px 14px; border:1px solid var(--_border);
  background:var(--_surface); color:inherit; text-decoration:none; cursor:pointer; }
button.primary, a.primary { background:var(--_accent); color:var(--_accent-text); border-color:var(--_accent); }
button:disabled { opacity:.5; cursor:not-allowed; }
.compare { position:relative; margin-top:12px; border-radius:calc(var(--_radius) - 4px); overflow:hidden; background:#eee; user-select:none; touch-action:none; }
.compare img { display:block; width:100%; height:auto; }
.compare .before { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; clip-path:inset(0 calc(100% - var(--pos,50%)) 0 0); }
.compare .handle { position:absolute; top:0; bottom:0; left:var(--pos,50%); width:2px; background:#fff; box-shadow:0 0 4px rgba(0,0,0,.5); pointer-events:none; }
.compare .tag { position:absolute; top:8px; font-size:.75rem; background:rgba(0,0,0,.55); color:#fff; padding:2px 8px; border-radius:99px; }
.compare .tag.l { left:8px; } .compare .tag.r { right:8px; }
.compare input[type=range] { position:absolute; inset:0; width:100%; height:100%; opacity:0; cursor:ew-resize; margin:0; }
.pair { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:12px; }
.pair figure { margin:0; position:relative; background:#f4f1ec; border-radius:calc(var(--_radius) - 4px); overflow:hidden;
  display:flex; align-items:center; justify-content:center; aspect-ratio:1; }
.pair img { max-width:100%; max-height:100%; display:block; }
.pair .tag { position:absolute; top:8px; left:8px; font-size:.75rem; background:rgba(0,0,0,.55); color:#fff; padding:2px 8px; border-radius:99px; }
@media (max-width:480px) { .pair { grid-template-columns:1fr; } }
.preview { margin-top:12px; max-height:360px; width:100%; object-fit:contain; border-radius:calc(var(--_radius) - 4px); background:#f4f1ec; }
.status { margin-top:10px; font-size:.875rem; color:var(--_muted); min-height:1.2em; }
.status.error { color:#b3261e; }
.score { font-weight:600; }
ul { list-style:none; padding:0; margin:8px 0 0; display:flex; flex-wrap:wrap; gap:6px; }
li { font-size:.8rem; border-radius:99px; padding:3px 10px; border:1px solid var(--_border); }
li.fixed { background:#e8f3ea; border-color:#bcdcc2; color:#1e5b2c; }
li.remaining { background:#fdf0e6; border-color:#f0cfb2; color:#7a3d0b; }
.spinner { width:14px; height:14px; border:2px solid var(--_border); border-top-color:var(--_accent); border-radius:50%;
  display:inline-block; animation:spin .8s linear infinite; vertical-align:-2px; margin-right:6px; }
@keyframes spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spinner { animation:none; } }
[hidden] { display:none !important; }
`;

class ImageStudioElement extends HTMLElement {
  static get observedAttributes() {
    return ["endpoint", "api-key", "preset", "presets"];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._file = null;
    this._result = null;
    this._urls = [];
  }

  get client() {
    return new ImageStudioClient({ endpoint: this.getAttribute("endpoint") || SCRIPT_ORIGIN, apiKey: this.getAttribute("api-key") });
  }

  connectedCallback() {
    this._render();
    this._loadPresets();
  }

  disconnectedCallback() {
    this._revoke();
  }

  attributeChangedCallback() {
    if (this.isConnected && this.shadowRoot.childElementCount) this._loadPresets();
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="box" part="box">
        <label class="drop" part="drop">
          <input type="file" accept="image/jpeg,image/png,image/webp">
          <strong>Choose a photo or drop it here</strong>
          <span>JPEG, PNG or WebP</span>
        </label>
        <img class="preview" alt="Selected photo" hidden>
        <div class="compare" hidden>
          <img class="after" alt="Enhanced photo">
          <img class="before" alt="Original photo">
          <div class="handle"></div>
          <span class="tag l">Before</span><span class="tag r">After</span>
          <input type="range" min="0" max="100" value="50" aria-label="Compare before and after">
        </div>
        <div class="pair" hidden>
          <figure><img class="p-before" alt="Original photo"><span class="tag">Before</span></figure>
          <figure><img class="p-after" alt="Enhanced photo"><span class="tag">After</span></figure>
        </div>
        <div class="row">
          <select aria-label="Style" hidden></select>
          <button class="primary go" disabled>Enhance</button>
          <a class="btn download" download hidden>Download</a>
          <button class="use primary" hidden>Use this photo</button>
          <button class="reset" hidden>Choose another</button>
        </div>
        <div class="status" role="status" aria-live="polite"></div>
        <ul class="issues"></ul>
      </div>`;
    const $ = (s) => this.shadowRoot.querySelector(s);
    this.$ = $;
    const input = $("input[type=file]");
    const drop = $(".drop");
    input.addEventListener("change", () => input.files[0] && this._select(input.files[0]));
    drop.addEventListener("dragover", (e) => {
      e.preventDefault();
      drop.classList.add("over");
    });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      drop.classList.remove("over");
      const f = e.dataTransfer.files[0];
      if (f) this._select(f);
    });
    $(".go").addEventListener("click", () => this._process());
    $(".reset").addEventListener("click", () => this.reset());
    $(".use").addEventListener("click", () => this._use());
    const range = $(".compare input");
    range.addEventListener("input", () => $(".compare").style.setProperty("--pos", `${range.value}%`));
  }

  async _loadPresets() {
    const select = this.$("select");
    const fixed = this.getAttribute("preset");
    if (fixed) {
      select.hidden = true;
      return;
    }
    try {
      const all = await this.client.presets();
      const allow = (this.getAttribute("presets") || "").split(",").map((s) => s.trim()).filter(Boolean);
      const names = Object.keys(all).filter((n) => !allow.length || allow.includes(n));
      select.innerHTML = names.map((n) => `<option value="${esc(n)}" title="${esc(all[n].description || "")}">${esc(n)}</option>`).join("");
      select.hidden = names.length < 2;
    } catch (err) {
      this._status(`Could not reach Image Studio: ${esc(err.message)}`, true);
    }
  }

  _url(blob) {
    const u = URL.createObjectURL(blob);
    this._urls.push(u);
    return u;
  }

  _revoke() {
    this._urls.forEach((u) => URL.revokeObjectURL(u));
    this._urls = [];
  }

  _status(text, error = false, busy = false) {
    const el = this.$(".status");
    el.classList.toggle("error", error);
    el.innerHTML = busy ? `<span class="spinner"></span>${text}` : text;
  }

  _select(file) {
    if (!/^image\//.test(file.type)) {
      this._status("Please choose an image file.", true);
      return;
    }
    this.reset(false);
    this._file = file;
    const preview = this.$(".preview");
    preview.src = this._url(file);
    preview.hidden = false;
    this.$(".drop").hidden = true;
    this.$(".go").disabled = false;
    this.$(".reset").hidden = false;
    this._status(`${esc(file.name)} - ${(file.size / 1048576).toFixed(1)} MB`);
  }

  reset(clearStatus = true) {
    this._revoke();
    this._file = this._result = null;
    const $ = this.$;
    $(".preview").hidden = true;
    $(".compare").hidden = true;
    $(".pair").hidden = true;
    $(".drop").hidden = false;
    $(".go").disabled = true;
    $(".download").hidden = $(".use").hidden = $(".reset").hidden = true;
    $(".issues").innerHTML = "";
    $("input[type=file]").value = "";
    if (clearStatus) this._status("");
  }

  async _process() {
    if (!this._file) return;
    const $ = this.$;
    const preset = this.getAttribute("preset") || $("select").value || "default";
    $(".go").disabled = true;
    this._status("Enhancing... this can take up to a minute for large photos.", false, true);
    try {
      const r = await this.client.process(this._file, { preset, format: this.getAttribute("format") });
      this._result = r;
      const rep = r.report;
      const before = $(".preview").src;
      const after = this._url(r.blob);
      // A slider only makes sense when both images show the same framing.
      const frame = rep.steps.find((s) => s.step === "frame");
      const [sw, sh] = rep.source.size;
      const sameFrame = frame && frame.region[0] <= 1 && frame.region[1] <= 1 && Math.abs(frame.region[2] - sw) <= 1 && Math.abs(frame.region[3] - sh) <= 1;
      $(".preview").hidden = true;
      $(".compare").hidden = !sameFrame;
      $(".pair").hidden = sameFrame;
      $(".after").src = $(".p-after").src = after;
      $(".before").src = $(".p-before").src = before;
      const dl = $(".download");
      dl.href = after;
      dl.download = r.file.name;
      dl.hidden = false;
      $(".use").hidden = !this.getAttribute("target");
      this._status(`<span class="score">Quality ${rep.source.score} &rarr; ${rep.result.score}</span> &middot; ${r.width}&times;${r.height}`);
      const label = (c) => esc(LABELS[c] || c.replace(/_/g, " "));
      $(".issues").innerHTML =
        rep.fixed.map((c) => `<li class="fixed">&#10003; ${label(c)}</li>`).join("") +
        rep.result.issues.map((i) => `<li class="remaining" title="${esc(i.message)}">! ${label(i.code)}</li>`).join("");
      this.dispatchEvent(new CustomEvent("image-studio:result", { bubbles: true, composed: true, detail: r }));
    } catch (err) {
      this._status(`Could not enhance this photo: ${esc(err.message)}`, true);
      this.dispatchEvent(new CustomEvent("image-studio:error", { bubbles: true, composed: true, detail: { error: err } }));
    } finally {
      $(".go").disabled = false;
    }
  }

  _use() {
    const target = document.querySelector(this.getAttribute("target"));
    if (!target || !this._result) return;
    const dt = new DataTransfer();
    dt.items.add(this._result.file);
    target.files = dt.files;
    target.dispatchEvent(new Event("change", { bubbles: true }));
    this._status("Enhanced photo attached.");
    this.dispatchEvent(new CustomEvent("image-studio:use", { bubbles: true, composed: true, detail: { file: this._result.file, report: this._result.report } }));
  }
}

if (!customElements.get("image-studio")) customElements.define("image-studio", ImageStudioElement);
