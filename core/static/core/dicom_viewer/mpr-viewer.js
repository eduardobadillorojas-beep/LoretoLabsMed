import { O as v, i as U, a as Z, b as H, R as j, V as D, c as W, s as X, P as k, W as M, Z as V, L as P, A as _, d as F, C as A, e as Y, g as K, f as J, t as Q, M as ee, h as te, j as R, k as ne } from "./chunks/VideoRedactionTool-BdY107HU.js";
const l = [
  ["LORETO_AXIAL", "mpr-axial", v.AXIAL],
  ["LORETO_CORONAL", "mpr-coronal", v.CORONAL],
  ["LORETO_SAGITAL", "mpr-sagital", v.SAGITTAL]
];
let h = !1, i = !1, s = null, p = null, O = null, w = l[0][0];
const T = /* @__PURE__ */ new Set();
let b = null, C = !1, u = null;
const z = "LORETO_MPR_ENGINE", B = "LORETO_MPR_TOOLS", E = {
  pan: k.toolName,
  wl: M.toolName,
  zoom: V.toolName,
  distancia: P.toolName,
  angulo: _.toolName,
  roi: F.toolName,
  cruces: A.toolName
}, re = {
  LORETO_AXIAL: { label: "AXIAL", top: "S", bottom: "I" },
  LORETO_CORONAL: { label: "CORONAL", top: "S", bottom: "I" },
  LORETO_SAGITAL: { label: "SAGITAL", top: "S", bottom: "I" }
};
function G(e) {
  return new URL(e, window.location.origin).href;
}
function N(e, t = !1) {
  const n = document.getElementById("mpr-loading");
  n && (n.hidden = !1, n.textContent = e, n.style.color = t ? "#fecaca" : "#d8e9f3");
}
function oe(e) {
  const t = document.getElementById("descargar-original")?.href;
  return e.series.find(
    (n) => n.instancias.some((r) => G(r.dicom_url) === t)
  ) || e.series.find((n) => n.apta_para_volumen);
}
function S(e) {
  w = e, l.forEach(([a, c]) => {
    document.getElementById(c)?.parentElement?.classList.toggle("selected", a === e);
  });
  const t = re[e], n = document.getElementById("mpr-slider-plane"), r = document.getElementById("mpr-slider-top"), o = document.getElementById("mpr-slider-bottom");
  n && (n.textContent = t?.label || "PLANO"), r && (r.textContent = t?.top || ""), o && (o.textContent = t?.bottom || ""), q();
}
function m() {
  return s?.getViewport(w);
}
function $(e) {
  if (!Object.hasOwn(E, e) || !u) return;
  const t = O === e;
  Object.values(E).forEach((o) => {
    try {
      u.setToolDisabled(o);
    } catch (a) {
      console.debug("Herramienta desactivada:", o, a);
    }
  }), t ? O = null : (u.setToolEnabled(E[e]), u.setToolActive(E[e], {
    bindings: [{ mouseButton: ee.Primary }]
  }), O = e), document.querySelectorAll(".tool-button").forEach((o) => {
    o.classList.toggle("active-tool", !t && o.dataset.tool === e), o.setAttribute("aria-pressed", String(!t && o.dataset.tool === e));
  });
  const n = {
    pan: "Mover",
    wl: "Ventana/nivel",
    zoom: "Zoom",
    distancia: "Regla",
    angulo: "Ángulo",
    roi: "ROI/HU",
    cruces: "Cruces enlazadas"
  }, r = document.getElementById("measurement-result");
  if (r && i) {
    const o = ["distancia", "angulo", "roi"].includes(e) ? "Dibuja la medición con el botón izquierdo sobre cualquier plano." : "Arrastra con el botón izquierdo sobre el plano deseado.";
    r.textContent = t ? "MPR · Herramienta desactivada. Usa la rueda para navegar o selecciona otra herramienta." : `MPR · Herramienta activa: ${n[e]}. ${o}`;
  }
}
function ie(e, t, n) {
  const r = () => S(e);
  n.addEventListener("pointerenter", r, !0), n.addEventListener("pointerdown", r, !0), n.parentElement?.addEventListener("pointerenter", r, !0), n.parentElement?.addEventListener("pointerdown", r, !0), n.addEventListener("wheel", (o) => {
    if (o.preventDefault(), S(e), o.ctrlKey) {
      const a = t.getZoom();
      t.setZoom(Math.max(0.2, Math.min(12, a * (o.deltaY < 0 ? 1.12 : 0.89))));
    } else
      I(t, o.deltaY > 0 ? 1 : -1);
    t.render();
  }, { passive: !1 }), n.addEventListener("dblclick", () => {
    t.resetCamera(), t.render();
  });
}
function q(e = m()) {
  if (!e) return;
  let t, n;
  try {
    const g = R(e, p, !1);
    t = g.currentStepIndex, n = g.numScrollSteps + 1;
  } catch {
    t = e.getCurrentImageIdIndex?.(), n = e.getNumberOfSlices?.();
  }
  const r = document.getElementById("contador-imagen");
  r && (r.textContent = Number.isFinite(t) && Number.isFinite(n) ? `MPR · Corte ${t + 1} de ${n}` : "MPR · Plano activo");
  const o = document.getElementById("slice-slider"), a = document.getElementById("mpr-slice-slider"), c = document.getElementById("slice-slider-value");
  Number.isFinite(t) && Number.isFinite(n) && (o && (o.max = String(n), o.value = String(t + 1)), c && (c.textContent = `${t + 1}/${n}`), a && (a.max = String(n), a.value = String(t + 1)));
}
function I(e, t) {
  e && (te(e, { delta: t, volumeId: p, scrollSlabs: !0 }), s?.renderViewports([e.id]), window.requestAnimationFrame(() => {
    e.render(), q(e);
  }));
}
function f() {
  C = !1, b && window.clearTimeout(b), b = null;
}
function ae() {
  f(), C = !0;
  const e = () => {
    if (!C || !i) return;
    const t = m();
    if (!t) return;
    let n, r;
    try {
      const c = R(t, p, !1);
      n = c.numScrollSteps + 1, r = c.currentStepIndex;
    } catch {
      n = t.getNumberOfSlices?.(), r = t.getCurrentImageIdIndex?.();
    }
    const o = Number.isFinite(n) && Number.isFinite(r) && r >= n - 1 ? -(n - 1) : 1;
    I(t, o);
    const a = Math.max(1, Number(document.getElementById("cine-velocidad")?.value || 5));
    b = window.setTimeout(() => window.requestAnimationFrame(e), 1e3 / a);
  };
  e();
}
function se() {
  [k, M, V, P, _, F, A].forEach((e) => {
    try {
      Y(e);
    } catch (t) {
      if (!String(t).toLowerCase().includes("already")) throw t;
    }
  }), u = K(B) || J(B), Object.values(E).forEach((e) => {
    u.hasTool?.(e) || (e === A.toolName ? u.addTool(e, {
      configuration: {
        getReferenceLineColor: (t) => ({
          LORETO_AXIAL: "rgb(239,68,68)",
          LORETO_CORONAL: "rgb(34,197,94)",
          LORETO_SAGITAL: "rgb(59,130,246)"
        })[t] || "rgb(34,211,238)",
        getReferenceLineControllable: () => !0,
        getReferenceLineDraggableRotatable: () => !0,
        getReferenceLineSlabThicknessControlsOn: () => !1
      }
    }) : u.addTool(e));
  }), l.forEach(([e]) => u.addViewport(e, z)), Q.setToolGroupToolStyles(B, {
    global: {
      color: "rgb(34,211,238)",
      colorHighlighted: "rgb(250,204,21)",
      colorSelected: "rgb(255,255,255)",
      lineWidth: "2",
      textBoxColor: "rgb(255,255,255)",
      textBoxBackground: "rgba(0,0,0,0.82)",
      textBoxLinkColor: "rgb(34,211,238)",
      textBoxShadow: !0,
      textBoxFontSize: "14px",
      textBoxFontFamily: "Arial, sans-serif"
    }
  });
}
function x(e, t) {
  if (!i || !s || !Number.isFinite(e) || !Number.isFinite(t)) return;
  const n = { lower: e - t / 2, upper: e + t / 2 };
  l.forEach(([r]) => {
    const o = s.getViewport(r);
    o.setProperties({ voiRange: n }), o.render();
  });
}
async function ce() {
  if (!h) {
    h = !0, N("Leyendo geometría y píxeles DICOM…");
    try {
      await U(), await Z({ maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2)) }), await H();
      const e = document.querySelector(".dicom-wrap"), t = await fetch(e.dataset.manifestUrl, { credentials: "same-origin" });
      if (!t.ok) throw new Error(`El manifiesto respondió ${t.status}.`);
      const n = await t.json(), r = oe(n);
      if (!r) throw new Error("Este estudio no contiene una serie volumétrica compatible.");
      if (!r.apta_para_volumen)
        throw new Error("La serie no contiene posición y orientación suficientes para MPR.");
      if (r.instancias.length < 3) throw new Error("Se necesitan por lo menos tres cortes para reconstruir un volumen.");
      const o = r.instancias.map((d) => `wadouri:${G(d.dicom_url)}`);
      p = `cornerstoneStreamingImageVolume:loreto-${n.estudio.id}-${r.id}`, s = new j(z), s.setViewports(l.map(([d, L, y]) => ({
        viewportId: d,
        element: document.getElementById(L),
        type: D.ORTHOGRAPHIC,
        defaultOptions: { orientation: y, background: [0, 0, 0] }
      })));
      const a = await W(p, { imageIds: o });
      await X(s, [{ volumeId: p }], l.map(([d]) => d)), a.load(), se(), l.forEach(([d, L]) => {
        const y = s.getViewport(d);
        y.resetCamera(), ie(d, y, document.getElementById(L));
      }), s.renderViewports(l.map(([d]) => d)), document.getElementById("mpr-loading").hidden = !0, S(l[0][0]), $("wl");
      const c = Number(document.getElementById("window-center")?.value || r.instancias[0]?.window_center), g = Number(document.getElementById("window-width")?.value || r.instancias[0]?.window_width);
      x(c, g);
    } catch (e) {
      h = !1, console.error("Loreto One MPR:", e), N(`No fue posible crear la reconstrucción: ${e.message}`, !0);
    }
  }
}
function le() {
  const e = document.getElementById("mpr-grid"), t = document.getElementById("viewer-stage"), n = document.getElementById("activar-mpr");
  i = !i, i || f(), e.hidden = !i, t.hidden = i, n.classList.toggle("active", i), n.textContent = i ? "Vista convencional" : "MPR 3 planos", document.querySelector(".viewer-shell")?.classList.toggle("mpr-active", i), i && ce().then(() => {
    s?.resize(!0, !1), s?.renderViewports(l.map(([r]) => r));
  });
}
document.getElementById("activar-mpr")?.addEventListener("click", le);
const de = document.getElementById("corte-anterior")?.onclick, ue = document.getElementById("corte-siguiente")?.onclick, me = document.getElementById("cine-reproducir")?.onclick, ge = document.getElementById("cine-pausar")?.onclick;
document.getElementById("corte-anterior").onclick = (e) => {
  if (!i) return de?.call(e.currentTarget, e);
  f(), I(m(), -1);
};
document.getElementById("corte-siguiente").onclick = (e) => {
  if (!i) return ue?.call(e.currentTarget, e);
  f(), I(m(), 1);
};
document.getElementById("cine-pausar").onclick = (e) => {
  if (!i) return ge?.call(e.currentTarget, e);
  f();
};
document.getElementById("cine-reproducir").onclick = (e) => {
  if (!i) return me?.call(e.currentTarget, e);
  ae();
};
document.querySelectorAll(".tool-button").forEach((e) => {
  e.addEventListener("click", () => {
    i && $(e.dataset.tool);
  });
});
document.getElementById("mpr-slice-slider")?.addEventListener("input", (e) => {
  if (!i) return;
  f();
  const t = m();
  if (t)
    try {
      const n = R(t, p, !1), r = Number(e.currentTarget.value) - 1;
      I(t, r - n.currentStepIndex);
    } catch (n) {
      console.debug("Navegación vertical MPR:", n);
    }
});
document.getElementById("zoom-mas")?.addEventListener("click", () => {
  if (!i) return;
  const e = m();
  e.setZoom(Math.min(12, e.getZoom() * 1.2)), e.render();
});
document.getElementById("zoom-menos")?.addEventListener("click", () => {
  if (!i) return;
  const e = m();
  e.setZoom(Math.max(0.2, e.getZoom() / 1.2)), e.render();
});
document.getElementById("restablecer")?.addEventListener("click", () => {
  i && l.forEach(([e]) => {
    const t = s.getViewport(e);
    t.resetCamera(), t.resetProperties?.(), t.render();
  });
});
document.getElementById("borrar-mediciones")?.addEventListener("click", () => {
  if (!i) return;
  ne.removeAllAnnotations(), s?.renderViewports(l.map(([t]) => t));
  const e = document.getElementById("measurement-result");
  e && (e.textContent = "MPR · Mediciones eliminadas.");
});
document.getElementById("rotar")?.addEventListener("click", () => {
  if (!i) return;
  const e = m(), t = e?.getCamera?.();
  if (!t?.viewPlaneNormal || !t?.viewUp) return;
  const [n, r, o] = t.viewPlaneNormal, [a, c, g] = t.viewUp, d = [r * g - o * c, o * a - n * g, n * c - r * a];
  e.setCamera({ viewUp: d }), e.render();
});
document.getElementById("invertir")?.addEventListener("click", () => {
  if (!i) return;
  const e = m(), t = !T.has(w);
  e.setProperties({ invert: t }), t ? T.add(w) : T.delete(w), e.render();
});
document.querySelectorAll(".preset").forEach((e) => {
  e.addEventListener("click", () => x(Number(e.dataset.wc), Number(e.dataset.ww)));
});
document.getElementById("aplicar-ventana")?.addEventListener("click", () => {
  x(Number(document.getElementById("window-center").value), Number(document.getElementById("window-width").value));
});
window.addEventListener("resize", () => {
  !i || !s || (s.resize(!0, !1), s.renderViewports(l.map(([e]) => e)));
});
