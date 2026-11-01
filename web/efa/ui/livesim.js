
const TYPES = { uint32: Uint32Array, int16: Int16Array, uint16: Uint16Array, uint8: Uint8Array, float32: Float32Array };
export function decodeLive(buf) {
  const n = new DataView(buf).getUint32(0, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, n)));
  const arrays = {};
  for (const a of header.arrays || []) arrays[a.name] = new TYPES[a.type](buf, 4 + n + a.offset, a.length);
  return { header, arrays };
}
export function blendCss(look) {
  if (look?.kind === "dissolve") return "normal";
  const m = look?.look || look?.blend || "add";
  return m === "over" ? "normal" : String(m).startsWith("contrast") ? "screen" : "plus-lighter";
}
function gradient(stops, t, out) {
  const s = stops?.length ? stops : [[0, [1, 1, 1]], [1, [1, 1, 1]]];
  if (t <= s[0][0]) { out[0] = s[0][1][0]; out[1] = s[0][1][1]; out[2] = s[0][1][2]; return out; }
  for (let k = 1; k < s.length; k++) {
    if (t <= s[k][0]) {
      const f = (t - s[k - 1][0]) / Math.max(s[k][0] - s[k - 1][0], 1e-9);
      for (let c = 0; c < 3; c++) out[c] = s[k - 1][1][c] + (s[k][1][c] - s[k - 1][1][c]) * f;
      return out;
    }
  }
  const l = s[s.length - 1][1];
  out[0] = l[0]; out[1] = l[1]; out[2] = l[2];
  return out;
}

const SPLAT_VS = `#version 300 es
layout(location=0) in vec2 aCorner;
layout(location=1) in vec4 aPos;     // x, y (plate px), sigma or radius (plate px), shape (0 gaussian, 1 solid)
layout(location=2) in vec4 aCol;     // rgb, opacity at the centre
uniform vec2 uRes; uniform float uK;
out vec2 vD; out vec4 vCol; flat out float vShape; out float vSig;
void main() {
  float s0 = aPos.z * uK;
  float sig = aPos.w > 0.5 ? max(s0, 0.5) : max(s0, 0.6);
  float peak = aCol.a * (aPos.w > 0.5 ? 1.0 : (s0 * s0) / (sig * sig));   // finer than the raster: same mass, wider
  float reach = aPos.w > 0.5 ? sig + 1.0 : 3.5 * sig + 1.0;
  vec2 p = aPos.xy * uK + aCorner * reach;
  vD = aCorner * reach; vSig = sig; vShape = aPos.w; vCol = vec4(aCol.rgb, peak);
  gl_Position = vec4(p.x / uRes.x * 2.0 - 1.0, 1.0 - p.y / uRes.y * 2.0, 0.0, 1.0);
}`;
const SPLAT_FS = `#version 300 es
precision highp float;
in vec2 vD; in vec4 vCol; flat in float vShape; in float vSig; out vec4 o;
void main() {
  float r = length(vD);
  float w = vShape > 0.5 ? clamp(vSig + 0.5 - r, 0.0, 1.0) : exp(-r * r / (2.0 * vSig * vSig));
  w *= vCol.a;
  o = vec4(vCol.rgb * w, w);
}`;
const FULL_VS = `#version 300 es
void main() { vec2 p = vec2[3](vec2(-1.,-1.), vec2(3.,-1.), vec2(-1.,3.))[gl_VertexID]; gl_Position = vec4(p, 0., 1.); }`;
const BLUR_FS = `#version 300 es
precision highp float;
uniform sampler2D uTex; uniform vec2 uDir; uniform float uSig; uniform ivec2 uSize; out vec4 o;
void main() {
  ivec2 p = ivec2(gl_FragCoord.xy);
  int R = min(int(ceil(3.0 * uSig)), 160);
  vec4 s = vec4(0.0); float ws = 0.0;
  for (int i = -R; i <= R; i++) {
    float w = exp(-float(i * i) / (2.0 * uSig * uSig));
    ws += w;
    ivec2 q = p + ivec2(uDir) * i;
    if (q.x >= 0 && q.y >= 0 && q.x < uSize.x && q.y < uSize.y) s += w * texelFetch(uTex, q, 0);   // zero outside (BORDER_CONSTANT)
  }
  o = s / ws;
}`;
const RESOLVE_FS = `#version 300 es
precision highp float;
uniform sampler2D uTex, uMask; uniform bool uBlob, uDissolve; uniform float uOp, uChoke, uSoft, uFill, uGlow, uDark;
uniform vec3 uGlowC; uniform vec2 uRes; out vec4 o;
void main() {
  vec4 b = texelFetch(uTex, ivec2(gl_FragCoord.xy), 0);
  float a = b.a;
  if (uDissolve) {                   // dissolve: particles over the hole (dark here, the run fills it), the band's glow added
    vec2 m = texture(uMask, vec2(gl_FragCoord.x / uRes.x, 1.0 - gl_FragCoord.y / uRes.y)).rg;
    float pa = min(a, 1.0);
    vec3 pc = b.rgb / max(a, 1.0);
    o = vec4(pc + m.g * uGlowC * uGlow, pa + (1.0 - pa) * m.r * uDark);
    return;
  }
  if (uBlob) {
    float op = max(uOp, 1e-3);
    float x = clamp((a / op - (uChoke - uSoft)) / max(2.0 * uSoft, 1e-3), 0.0, 1.0);
    float a2 = x * x * (3.0 - 2.0 * x) * (uFill * op + (1.0 - uFill) * clamp(a, 0.0, 1.0));
    o = vec4(b.rgb / max(a, 1e-3) * a2, a2);
  } else {
    o = vec4(b.rgb / max(a, 1.0), min(a, 1.0));   // overlapping sprites: mean colour, alpha at most 1
  }
}`;

function program(gl, vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src);
    gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    gl.attachShader(p, s);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name); }
  return { p, u };
}

const REF = 1080;
const MAX_SIDE = 1280;
export class LiveSim {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, alpha: true, antialias: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error("WebGL2 is not available");
    this.gl = gl;
    this.float = !!gl.getExtension("EXT_color_buffer_float") || !!gl.getExtension("EXT_color_buffer_half_float");
    this.splat = program(gl, SPLAT_VS, SPLAT_FS);
    this.blur = program(gl, FULL_VS, BLUR_FS);
    this.resolve = program(gl, FULL_VS, RESOLVE_FS);
    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    const corner = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, corner);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    this.inst = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 4, gl.FLOAT, false, 32, 0);
    gl.vertexAttribDivisor(1, 1);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 4, gl.FLOAT, false, 32, 16);
    gl.vertexAttribDivisor(2, 1);
    gl.bindVertexArray(null);
    this.empty = gl.createVertexArray();
    this.buf = new Float32Array(8 * 4096);
    this.count = 0;
    this.buf2 = new Float32Array(8 * 1024);
    this.count2 = 0;
    this.sel = 0;
    this.targets = [];
    this.data = null;
    this.look = {};
    this.drawn = -1;
  }
  destroy() { this.gl.getExtension("WEBGL_lose_context")?.loseContext(); }
  get frames() { return this.data?.header.n || 0; }
  setData(d) {
    this.data = d;
    const A = d.arrays, n = d.header.n;
    this.paths = Array.from({ length: n }, () => []);
    const P = A.paths || [];
    for (let j = 0; j + 3 <= P.length;) {
      const f = P[j] | 0, m = P[j + 1] | 0;
      if (f >= 0 && f < n) this.paths[f].push([j + 3, m, P[j + 2]]);
      j += 3 + 3 * m;
    }
    const K = A.cracks || [], C = A.cam || [];
    this.crackRows = Math.floor(K.length / 7);
    this.crackBorn = new Uint32Array(n);
    for (let f = 0, r = 0; f < n; f++) {
      while (r < this.crackRows && K[r * 7] <= f) r++;
      this.crackBorn[f] = r;
    }
    this.crackCam = C.length >= n * 6 ? C : null;
    this.size(d.header.W, d.header.H);
    this.drawn = -1;
  }
  setLook(look) { this.look = look || {}; this.drawn = -1; }
  size(W, H) {
    const k = Math.min(1, MAX_SIDE / Math.max(W, H));
    const w = Math.max(1, Math.round(W * k)), h = Math.max(1, Math.round(H * k));
    if (this.canvas.width === w && this.canvas.height === h && this.targets.length) return;
    this.k = k;
    this.canvas.width = w; this.canvas.height = h;
    const gl = this.gl;
    for (const t of this.targets) { gl.deleteTexture(t.tex); gl.deleteFramebuffer(t.fb); }
    this.targets = [0, 1, 2].map(() => {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, this.float ? gl.RGBA16F : gl.RGBA8, w, h, 0, gl.RGBA, this.float ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE, null);
      for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
      const fb = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
      gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
      return { tex, fb };
    });
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }
  push(x, y, sig, r, g, b, a, shape = 0) {
    if (a <= 1e-4) return;
    const bk = this.sel ? "buf2" : "buf", ck = this.sel ? "count2" : "count";
    if ((this[ck] + 1) * 8 > this[bk].length) { const nb = new Float32Array(this[bk].length * 2); nb.set(this[bk]); this[bk] = nb; }
    const o = this[ck] * 8;
    const B = this[bk];
    B[o] = x; B[o + 1] = y; B[o + 2] = sig; B[o + 3] = shape; B[o + 4] = r; B[o + 5] = g; B[o + 6] = b; B[o + 7] = a;
    this[ck]++;
  }
  line(x0, y0, x1, y1, sig, c, a0, a1 = a0) {
    const ln = Math.hypot(x1 - x0, y1 - y0);
    const k = Math.min(400, Math.max(1, Math.ceil(ln / Math.max(0.6 * sig, 0.5))));
    const d = ln / k, short = ln < 0.5 * sig;
    for (let m = 0; m < k; m++) {
      const u = (m + 0.5) / k, aa = a0 + (a1 - a0) * u;
      const peak = short ? aa / k : aa * Math.max(d, 1e-3) / (Math.sqrt(2 * Math.PI) * sig);
      this.push(x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, sig, c[0], c[1], c[2], peak);
    }
  }
  find(f, id) {
    const A = this.data.arrays;
    let lo = A.offs[f], hi = A.offs[f + 1] - 1;
    while (lo <= hi) { const m = (lo + hi) >> 1, v = A.id[m]; if (v === id) return m; if (v < id) lo = m + 1; else hi = m - 1; }
    return -1;
  }
  colour(id, age, out) {
    const L = this.look, A = this.data.arrays;
    gradient(L.colors, age, out);
    const m = +L.plate_color || 0;
    if (m > 0 && A.pcol?.length > id * 3 + 2) for (let c = 0; c < 3; c++) out[c] = out[c] * (1 - m) + (A.pcol[id * 3 + c] / 255) * out[c] * m;
    const cv = +L.color_var || 0;
    if (cv > 0) { const f = 1 + cv * ((A.rnd[id] ?? 128) / 255 - 0.5) * 2; for (let c = 0; c < 3; c++) out[c] *= f; }
    const g = L.glow ?? 1;
    for (let c = 0; c < 3; c++) out[c] = Math.min(Math.max(out[c], 0), 4) * g;
    return out;
  }
  build(i) {
    this.count = 0;
    this.count2 = 0;
    this.sel = 0;
    const A = this.data.arrays, H = this.data.header, L = this.look, fps = H.fps;
    if (H.kind === "dissolve") {
      const blur = L.blur || 0, sig = blur > 0.35 ? blur : 0.5, norm = blur > 0.35 ? 1 / (2 * Math.PI * blur * blur) : 1;
      for (let j = A.offs[i]; j < A.offs[i + 1]; j++)
        this.push(A.x[j] / 8, A.y[j] / 8, sig, A.col[3 * j] / 255, A.col[3 * j + 1] / 255, A.col[3 * j + 2] / 255, (A.a[j] / 255) * norm);
      return;
    }
    const spr = L.sprite || "soft";
    const col = [0, 0, 0];
    const life = (+L.blob || 0) > 0 && (+L.blob_life || 0) > 0 ? +L.blob_life : 0;
    for (let j = A.offs[i]; j < A.offs[i + 1]; j++) {
      const al0 = A.a[j] / 255;
      if (!life) { this.sel = 0; this.one(j, i, al0, spr, col); continue; }
      const young = Math.min(1, Math.max(0, (life - A.age[j] / 255) / (0.5 * life)));
      this.sel = 0; this.one(j, i, al0 * young, spr, col);
      this.sel = 1; this.one(j, i, al0 * (1 - young), spr, col);
    }
    this.sel = 0;
    this.paths_(i, L);
  }
  one(j, i, al, spr, col) {
    if (al <= 1e-4) return;
    const A = this.data.arrays, L = this.look, fps = this.data.header.fps;
    {
      const id = A.id[j], x = A.x[j] / 8, y = A.y[j] / 8, rs = A.r[j] / 16;
      const c = this.colour(id, A.age[j] / 255, col);
      if (spr === "dot") this.push(x, y, Math.max(0.5 * rs, 0.6), c[0], c[1], c[2], al);
      else if (spr === "chunk") this.push(x, y, Math.max(rs, 0.8), c[0], c[1], c[2], al, 1);
      else if (spr === "flake") { this.push(x, y, Math.max(0.45 * rs, 0.6), c[0], c[1], c[2], al); this.push(x, y, Math.max(rs, 1), c[0], c[1], c[2], 0.3 * al); }
      else if (spr === "puff") {
        const rot = A.rot[j] / 255 * 2 * Math.PI, rnd = (A.rnd[id] ?? 128) / 255;
        this.push(x, y, Math.max(0.7 * rs, 0.8), c[0], c[1], c[2], 0.6 * al);
        for (let q = 0; q < 4; q++) {
          const ang = rot + q * Math.PI / 2 + rnd * 1.3, off = rs * (0.45 + 0.25 * Math.sin(rnd * 7 + q));
          this.push(x + Math.cos(ang) * off, y + Math.sin(ang) * off, Math.max(0.5 * rs, 0.6), c[0], c[1], c[2], 0.45 * al);
        }
      } else if (spr === "streak" || spr === "spark") {
        const s2 = Math.max(+L.shutter || 0, 0.3) / fps;
        this.line(x - A.vx[j] * s2, y - A.vy[j] * s2, x, y, Math.max(0.5 * rs, 0.5), c, 0.15 * al, al);
        if (spr === "spark") this.push(x, y, Math.max(0.8 * rs, 0.7), c[0], c[1], c[2], al);
      } else this.push(x, y, Math.max(0.6 * (spr === "wisp" ? 1.6 * rs : rs), 0.6), c[0], c[1], c[2], al);
      const T = L.trail | 0;
      if (T > 0) {
        const j0 = Math.max(0, i - T), steps = i - j0 + 1, sig = Math.max(0.45 * rs, 0.5);
        let px = null, py = null;
        for (let s = 0; s < steps; s++) {
          const f = j0 + s, k = f === i ? j : this.find(f, id);
          if (k < 0) { px = null; continue; }
          const qx = A.x[k] / 8, qy = A.y[k] / 8;
          if (px !== null) this.line(px, py, qx, qy, sig, c, 0.6 * al * s / steps, 0.6 * al * (s + 1) / steps);
          px = qx; py = qy;
        }
      }
    }
  }
  paths_(i, L) {
    const A = this.data.arrays;
    const P = A.paths;
    const K = A.cracks, rows = this.crackCam ? this.crackBorn[i] : 0;
    if (K?.length && rows) {
      const c0 = gradient(L.colors, 0, [0, 0, 0]).map((v) => v * (L.glow ?? 1));
      const m = this.crackCam, o = i * 6;
      const sx = (x, y) => m[o] * x + m[o + 1] * y + m[o + 2], sy = (x, y) => m[o + 3] * x + m[o + 4] * y + m[o + 5];
      for (let r = 0; r < rows; r++) {
        const b = r * 7, w = K[b + 1], a = K[b + 2];
        const x0 = sx(K[b + 3], K[b + 4]), y0 = sy(K[b + 3], K[b + 4]), x1 = sx(K[b + 5], K[b + 6]), y1 = sy(K[b + 5], K[b + 6]);
        this.line(x0, y0, x1, y1, Math.max(0.5, 0.5 * w), c0, a, a);
        this.line(x0, y0, x1, y1, Math.max(2, 2.5 * w), c0, 0.1 * a, 0.1 * a);
      }
    }
    if (P?.length && this.paths[i]?.length) {
      const c0 = gradient(L.colors, 0, [0, 0, 0]).map((v) => v * (L.glow ?? 1));
      for (const [o, m, w] of this.paths[i]) {
        for (let v = 0; v + 1 < m; v++) {
          const a = o + 3 * v, b = a + 3;
          this.line(P[a], P[a + 1], P[b], P[b + 1], Math.max(0.5, 0.5 * w), c0, P[a + 2], P[b + 2]);
          if (m > 2 || v === 0) this.line(P[a], P[a + 1], P[b], P[b + 1], Math.max(2, 2.5 * w), c0, 0.1 * P[a + 2], 0.1 * P[b + 2]);
        }
      }
    }
  }
  draw(i) {
    if (!this.data || !this.frames) return;
    i = Math.max(0, Math.min(this.frames - 1, i | 0));
    if (i === this.drawn) return;
    this.drawn = i;
    this.build(i);
    const gl = this.gl, w = this.canvas.width, h = this.canvas.height, L = this.look;
    const [t0, t1] = this.targets;
    gl.bindFramebuffer(gl.FRAMEBUFFER, t0.fb);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (this.count) {
      gl.useProgram(this.splat.p);
      gl.uniform2f(this.splat.u.uRes, w, h);
      gl.uniform1f(this.splat.u.uK, this.k);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.bindVertexArray(this.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
      gl.bufferData(gl.ARRAY_BUFFER, this.buf.subarray(0, this.count * 8), gl.STREAM_DRAW);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.count);
      gl.bindVertexArray(null);
      gl.disable(gl.BLEND);
    }
    const blob = (+L.blob || 0) > 0;
    gl.bindVertexArray(this.empty);
    if (blob) {
      const sig = Math.max(L.blob * Math.min(this.data.header.W, this.data.header.H) / REF * this.k, 0.3);
      gl.useProgram(this.blur.p);
      gl.uniform1f(this.blur.u.uSig, sig);
      gl.uniform2i(this.blur.u.uSize, w, h);
      gl.uniform1i(this.blur.u.uTex, 0);
      gl.activeTexture(gl.TEXTURE0);
      for (const [src, dst, dir] of [[t0, t1, [1, 0]], [t1, t0, [0, 1]]]) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, dst.fb);
        gl.bindTexture(gl.TEXTURE_2D, src.tex);
        gl.uniform2f(this.blur.u.uDir, dir[0], dir[1]);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, w, h);
    gl.useProgram(this.resolve.p);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, t0.tex);
    gl.uniform1i(this.resolve.u.uTex, 0);
    gl.uniform1i(this.resolve.u.uBlob, blob ? 1 : 0);
    gl.uniform1f(this.resolve.u.uOp, L.opacity ?? 1);
    gl.uniform1f(this.resolve.u.uChoke, L.blob_choke ?? 0.35);
    gl.uniform1f(this.resolve.u.uSoft, L.blob_soft ?? 0.12);
    gl.uniform1f(this.resolve.u.uFill, L.blob_fill ?? 1);
    const dis = this.data.header.kind === "dissolve";
    gl.uniform1i(this.resolve.u.uDissolve, dis ? 1 : 0);
    if (dis) {
      const [mw, mh] = this.data.header.small, A = this.data.arrays, sz = mw * mh;
      const [bx, by, bw, bh] = this.data.header.box || [0, 0, mw, mh];
      const rg = this.maskBuf?.length === 2 * sz ? this.maskBuf : (this.maskBuf = new Uint8Array(2 * sz));
      rg.fill(0);
      for (let r = 0, o = i * bw * bh; r < bh; r++) {
        for (let c = 0, q = 2 * ((by + r) * mw + bx); c < bw; c++, o++, q += 2) { rg[q] = A.gone[o]; rg[q + 1] = A.band[o]; }
      }
      if (!this.maskTex) this.maskTex = gl.createTexture();
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.maskTex);
      gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG8, mw, mh, 0, gl.RG, gl.UNSIGNED_BYTE, rg);
      for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, p, gl.LINEAR);
      for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, p, gl.CLAMP_TO_EDGE);
      gl.uniform1i(this.resolve.u.uMask, 1);
      gl.uniform2f(this.resolve.u.uRes, w, h);
      gl.uniform1f(this.resolve.u.uGlow, L.glow || 0);
      gl.uniform3fv(this.resolve.u.uGlowC, L.glow_color || [1, 0.55, 0.15]);
      gl.uniform1f(this.resolve.u.uDark, 0.7);
      gl.activeTexture(gl.TEXTURE0);
    }
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (this.count2 && !dis) {
      const t2 = this.targets[2];
      gl.bindFramebuffer(gl.FRAMEBUFFER, t2.fb);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(this.splat.p);
      gl.uniform2f(this.splat.u.uRes, w, h);
      gl.uniform1f(this.splat.u.uK, this.k);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.bindVertexArray(this.vao);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
      gl.bufferData(gl.ARRAY_BUFFER, this.buf2.subarray(0, this.count2 * 8), gl.STREAM_DRAW);
      gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.count2);
      gl.bindVertexArray(this.empty);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.useProgram(this.resolve.p);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, t2.tex);
      gl.uniform1i(this.resolve.u.uTex, 0);
      gl.uniform1i(this.resolve.u.uBlob, 0);
      gl.uniform1i(this.resolve.u.uDissolve, 0);
      if ((L.look || L.blend) === "over") gl.blendFunc(gl.ONE_MINUS_DST_ALPHA, gl.ONE);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.disable(gl.BLEND);
    }
    gl.bindVertexArray(null);
  }
}
