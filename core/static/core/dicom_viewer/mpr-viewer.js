import { O, i as D, a as H, b as j, R as W, V as X, c as Y, s as K, P as M, W as P, Z as V, L as _, A as F, d as z, C as v, e as J, g as Q, f as ee, t as te, E as ne, M as re, h as oe, j as x, k as ie } from "./chunks/VideoRedactionTool-PF0Cw2kQ.js";
const l = [
  ["LORETO_AXIAL", "mpr-axial", O.AXIAL],
  ["LORETO_CORONAL", "mpr-coronal", O.CORONAL],
  ["LORETO_SAGITAL", "mpr-sagital", O.SAGITTAL]
];
let T = !1, i = !1, s = null, p = null, B = null, w = l[0][0];
const A = /* @__PURE__ */ new Set();
let L = null, C = !1, u = null, y = null;
const G = "LORETO_MPR_ENGINE", R = "LORETO_MPR_TOOLS", E = {
  pan: M.toolName,
  wl: P.toolName,
  zoom: V.toolName,
  distancia: _.toolName,
  angulo: F.toolName,
  roi: z.toolName,
  cruces: v.toolName
}, ae = {
  LORETO_AXIAL: { label: "AXIAL", top: "S", bottom: "I" },
  LORETO_CORONAL: { label: "CORONAL", top: "S", bottom: "I" },
  LORETO_SAGITAL: { label: "SAGITAL", top: "S", bottom: "I" }
};
function $(e) {
  return new URL(e, window.location.origin).href;
}
function k(e, t = !1) {
  const n = document.getElementById("mpr-loading");
  n && (n.hidden = !1, n.textContent = e, n.style.color = t ? "#fecaca" : "#d8e9f3");
}
function se(e) {
  const t = document.getElementById("descargar-original")?.href;
  return e.series.find(
    (n) => n.instancias.some((r) => $(r.dicom_url) === t)
  ) || e.series.find((n) => n.apta_para_volumen);
}
function S(e) {
  w = e, l.forEach(([a, c]) => {
    document.getElementById(c)?.parentElement?.classList.toggle("selected", a === e);
  });
  const t = ae[e], n = document.getElementById("mpr-slider-plane"), r = document.getElementById("mpr-slider-top"), o = document.getElementById("mpr-slider-bottom");
  n && (n.textContent = t?.label || "PLANO"), r && (r.textContent = t?.top || ""), o && (o.textContent = t?.bottom || ""), Z();
}
function m() {
  return s?.getViewport(w);
}
function q(e = m()) {
  !i || !s || (y && window.cancelAnimationFrame(y), y = window.requestAnimationFrame(() => {
    y = null, s.renderViewports(l.map(([t]) => t)), Z(e);
  }));
}
function U(e) {
  if (!Object.hasOwn(E, e) || !u) return;
  const t = B === e;
  if (Object.values(E).forEach((o) => {
    try {
      u.setToolDisabled(o);
    } catch (a) {
      console.debug("Herramienta desactivada:", o, a);
    }
  }), t ? B = null : (u.setToolEnabled(E[e]), u.setToolActive(E[e], {
    bindings: [{ mouseButton: re.Primary }]
  }), B = e), e !== "cruces")
    try {
      u.setToolEnabled(v.toolName);
    } catch (o) {
      console.debug("Cruces MPR enlazadas:", o);
    }
  document.querySelectorAll(".tool-button").forEach((o) => {
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
function ce(e, t, n) {
  const r = () => S(e);
  new Set([n, n.parentElement].filter(Boolean)).forEach((a) => {
    a.addEventListener("pointerenter", r, !0), a.addEventListener("pointerdown", r, !0), a.addEventListener("mousedown", r, !0), a.addEventListener("touchstart", r, { capture: !0, passive: !0 }), a.addEventListener("click", r, !0);
  }), n.addEventListener(ne.CAMERA_MODIFIED, () => {
    q(t);
  }), n.addEventListener("wheel", (a) => {
    if (a.preventDefault(), S(e), a.ctrlKey) {
      const c = t.getZoom();
      t.setZoom(Math.max(0.2, Math.min(12, c * (a.deltaY < 0 ? 1.12 : 0.89))));
    } else
      I(t, a.deltaY > 0 ? 1 : -1);
    t.render();
  }, { passive: !1 }), n.addEventListener("dblclick", () => {
    t.resetCamera(), t.render();
  });
}
function Z(e = m()) {
  if (!e) return;
  let t, n;
  try {
    const g = x(e, p, !1);
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
  e && (oe(e, { delta: t, volumeId: p, scrollSlabs: !0 }), q(e));
}
function f() {
  C = !1, L && window.clearTimeout(L), L = null;
}
function le() {
  f(), C = !0;
  const e = () => {
    if (!C || !i) return;
    const t = m();
    if (!t) return;
    let n, r;
    try {
      const c = x(t, p, !1);
      n = c.numScrollSteps + 1, r = c.currentStepIndex;
    } catch {
      n = t.getNumberOfSlices?.(), r = t.getCurrentImageIdIndex?.();
    }
    const o = Number.isFinite(n) && Number.isFinite(r) && r >= n - 1 ? -(n - 1) : 1;
    I(t, o);
    const a = Math.max(1, Number(document.getElementById("cine-velocidad")?.value || 5));
    L = window.setTimeout(() => window.requestAnimationFrame(e), 1e3 / a);
  };
  e();
}
function de() {
  [M, P, V, _, F, z, v].forEach((e) => {
    try {
      J(e);
    } catch (t) {
      if (!String(t).toLowerCase().includes("already")) throw t;
    }
  }), u = Q(R) || ee(R), Object.values(E).forEach((e) => {
    u.hasTool?.(e) || (e === v.toolName ? u.addTool(e, {
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
  }), l.forEach(([e]) => u.addViewport(e, G)), te.setToolGroupToolStyles(R, {
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
function N(e, t) {
  if (!i || !s || !Number.isFinite(e) || !Number.isFinite(t)) return;
  const n = { lower: e - t / 2, upper: e + t / 2 };
  l.forEach(([r]) => {
    const o = s.getViewport(r);
    o.setProperties({ voiRange: n }), o.render();
  });
}
async function ue() {
  if (!T) {
    T = !0, k("Leyendo geometría y píxeles DICOM…");
    try {
      await D(), await H({ maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2)) }), await j();
      const e = document.querySelector(".dicom-wrap"), t = await fetch(e.dataset.manifestUrl, { credentials: "same-origin" });
      if (!t.ok) throw new Error(`El manifiesto respondió ${t.status}.`);
      const n = await t.json(), r = se(n);
      if (!r) throw new Error("Este estudio no contiene una serie volumétrica compatible.");
      if (!r.apta_para_volumen)
        throw new Error("La serie no contiene posición y orientación suficientes para MPR.");
      if (r.instancias.length < 3) throw new Error("Se necesitan por lo menos tres cortes para reconstruir un volumen.");
      const o = r.instancias.map((d) => `wadouri:${$(d.dicom_url)}`);
      p = `cornerstoneStreamingImageVolume:loreto-${n.estudio.id}-${r.id}`, s = new W(G), s.setViewports(l.map(([d, h, b]) => ({
        viewportId: d,
        element: document.getElementById(h),
        type: X.ORTHOGRAPHIC,
        defaultOptions: { orientation: b, background: [0, 0, 0] }
      })));
      const a = await Y(p, { imageIds: o });
      await K(s, [{ volumeId: p }], l.map(([d]) => d)), a.load(), de(), l.forEach(([d, h]) => {
        const b = s.getViewport(d);
        b.resetCamera(), ce(d, b, document.getElementById(h));
      }), s.renderViewports(l.map(([d]) => d)), document.getElementById("mpr-loading").hidden = !0, S(l[0][0]), U("wl");
      const c = Number(document.getElementById("window-center")?.value || r.instancias[0]?.window_center), g = Number(document.getElementById("window-width")?.value || r.instancias[0]?.window_width);
      N(c, g);
    } catch (e) {
      T = !1, console.error("Loreto One MPR:", e), k(`No fue posible crear la reconstrucción: ${e.message}`, !0);
    }
  }
}
function me() {
  const e = document.getElementById("mpr-grid"), t = document.getElementById("viewer-stage"), n = document.getElementById("activar-mpr");
  i = !i, i || f(), e.hidden = !i, t.hidden = i, n.classList.toggle("active", i), n.textContent = i ? "Vista convencional" : "MPR 3 planos", document.querySelector(".viewer-shell")?.classList.toggle("mpr-active", i), i && ue().then(() => {
    s?.resize(!0, !1), s?.renderViewports(l.map(([r]) => r));
  });
}
document.getElementById("activar-mpr")?.addEventListener("click", me);
const ge = document.getElementById("corte-anterior")?.onclick, pe = document.getElementById("corte-siguiente")?.onclick, fe = document.getElementById("cine-reproducir")?.onclick, Ee = document.getElementById("cine-pausar")?.onclick;
document.getElementById("corte-anterior").onclick = (e) => {
  if (!i) return ge?.call(e.currentTarget, e);
  f(), I(m(), -1);
};
document.getElementById("corte-siguiente").onclick = (e) => {
  if (!i) return pe?.call(e.currentTarget, e);
  f(), I(m(), 1);
};
document.getElementById("cine-pausar").onclick = (e) => {
  if (!i) return Ee?.call(e.currentTarget, e);
  f();
};
document.getElementById("cine-reproducir").onclick = (e) => {
  if (!i) return fe?.call(e.currentTarget, e);
  le();
};
document.querySelectorAll(".tool-button").forEach((e) => {
  e.addEventListener("click", () => {
    i && U(e.dataset.tool);
  });
});
document.getElementById("mpr-slice-slider")?.addEventListener("input", (e) => {
  if (!i) return;
  f();
  const t = m();
  if (t)
    try {
      const n = x(t, p, !1), r = Number(e.currentTarget.value) - 1;
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
  ie.removeAllAnnotations(), s?.renderViewports(l.map(([t]) => t));
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
  const e = m(), t = !A.has(w);
  e.setProperties({ invert: t }), t ? A.add(w) : A.delete(w), e.render();
});
document.querySelectorAll(".preset").forEach((e) => {
  e.addEventListener("click", () => N(Number(e.dataset.wc), Number(e.dataset.ww)));
});
document.getElementById("aplicar-ventana")?.addEventListener("click", () => {
  N(Number(document.getElementById("window-center").value), Number(document.getElementById("window-width").value));
});
window.addEventListener("resize", () => {
  !i || !s || (s.resize(!0, !1), s.renderViewports(l.map(([e]) => e)));
});
