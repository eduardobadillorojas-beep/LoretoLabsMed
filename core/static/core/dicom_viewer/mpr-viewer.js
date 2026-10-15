import { O as h, i as U, a as Z, b as H, R as j, V as D, c as W, s as X, P as M, W as V, Z as k, L as P, A as _, d as F, C as L, e as Y, g as K, f as J, t as Q, M as ee, h as te, j as S, k as ne } from "./chunks/VideoRedactionTool-BdY107HU.js";
const c = [
  ["LORETO_AXIAL", "mpr-axial", h.AXIAL],
  ["LORETO_CORONAL", "mpr-coronal", h.CORONAL],
  ["LORETO_SAGITAL", "mpr-sagital", h.SAGITTAL]
];
let O = !1, i = !1, a = null, p = null, T = null, w = c[0][0];
const B = /* @__PURE__ */ new Set();
let y = null, C = !1, u = null;
const z = "LORETO_MPR_ENGINE", A = "LORETO_MPR_TOOLS", E = {
  pan: M.toolName,
  wl: V.toolName,
  zoom: k.toolName,
  distancia: P.toolName,
  angulo: _.toolName,
  roi: F.toolName,
  cruces: L.toolName
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
function R(e) {
  w = e, c.forEach(([s, l]) => {
    document.getElementById(l)?.parentElement?.classList.toggle("selected", s === e);
  });
  const t = re[e], n = document.getElementById("mpr-slider-plane"), r = document.getElementById("mpr-slider-top"), o = document.getElementById("mpr-slider-bottom");
  n && (n.textContent = t?.label || "PLANO"), r && (r.textContent = t?.top || ""), o && (o.textContent = t?.bottom || ""), q();
}
function m() {
  return a?.getViewport(w);
}
function $(e) {
  if (!Object.hasOwn(E, e) || !u) return;
  const t = T === e;
  if (Object.values(E).forEach((o) => {
    try {
      u.setToolDisabled(o);
    } catch (s) {
      console.debug("Herramienta desactivada:", o, s);
    }
  }), t ? T = null : (u.setToolEnabled(E[e]), u.setToolActive(E[e], {
    bindings: [{ mouseButton: ee.Primary }]
  }), T = e), e !== "cruces")
    try {
      u.setToolEnabled(L.toolName);
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
function ie(e, t, n) {
  const r = () => R(e);
  n.addEventListener("pointerenter", r, !0), n.addEventListener("pointerdown", r, !0), n.parentElement?.addEventListener("pointerenter", r, !0), n.parentElement?.addEventListener("pointerdown", r, !0), n.addEventListener("wheel", (o) => {
    if (o.preventDefault(), R(e), o.ctrlKey) {
      const s = t.getZoom();
      t.setZoom(Math.max(0.2, Math.min(12, s * (o.deltaY < 0 ? 1.12 : 0.89))));
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
    const g = S(e, p, !1);
    t = g.currentStepIndex, n = g.numScrollSteps + 1;
  } catch {
    t = e.getCurrentImageIdIndex?.(), n = e.getNumberOfSlices?.();
  }
  const r = document.getElementById("contador-imagen");
  r && (r.textContent = Number.isFinite(t) && Number.isFinite(n) ? `MPR · Corte ${t + 1} de ${n}` : "MPR · Plano activo");
  const o = document.getElementById("slice-slider"), s = document.getElementById("mpr-slice-slider"), l = document.getElementById("slice-slider-value");
  Number.isFinite(t) && Number.isFinite(n) && (o && (o.max = String(n), o.value = String(t + 1)), l && (l.textContent = `${t + 1}/${n}`), s && (s.max = String(n), s.value = String(t + 1)));
}
function I(e, t) {
  e && (te(e, { delta: t, volumeId: p, scrollSlabs: !0 }), a?.renderViewports(c.map(([n]) => n)), window.requestAnimationFrame(() => {
    a?.renderViewports(c.map(([n]) => n)), q(e);
  }));
}
function f() {
  C = !1, y && window.clearTimeout(y), y = null;
}
function ae() {
  f(), C = !0;
  const e = () => {
    if (!C || !i) return;
    const t = m();
    if (!t) return;
    let n, r;
    try {
      const l = S(t, p, !1);
      n = l.numScrollSteps + 1, r = l.currentStepIndex;
    } catch {
      n = t.getNumberOfSlices?.(), r = t.getCurrentImageIdIndex?.();
    }
    const o = Number.isFinite(n) && Number.isFinite(r) && r >= n - 1 ? -(n - 1) : 1;
    I(t, o);
    const s = Math.max(1, Number(document.getElementById("cine-velocidad")?.value || 5));
    y = window.setTimeout(() => window.requestAnimationFrame(e), 1e3 / s);
  };
  e();
}
function se() {
  [M, V, k, P, _, F, L].forEach((e) => {
    try {
      Y(e);
    } catch (t) {
      if (!String(t).toLowerCase().includes("already")) throw t;
    }
  }), u = K(A) || J(A), Object.values(E).forEach((e) => {
    u.hasTool?.(e) || (e === L.toolName ? u.addTool(e, {
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
  }), c.forEach(([e]) => u.addViewport(e, z)), Q.setToolGroupToolStyles(A, {
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
  if (!i || !a || !Number.isFinite(e) || !Number.isFinite(t)) return;
  const n = { lower: e - t / 2, upper: e + t / 2 };
  c.forEach(([r]) => {
    const o = a.getViewport(r);
    o.setProperties({ voiRange: n }), o.render();
  });
}
async function ce() {
  if (!O) {
    O = !0, N("Leyendo geometría y píxeles DICOM…");
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
      p = `cornerstoneStreamingImageVolume:loreto-${n.estudio.id}-${r.id}`, a = new j(z), a.setViewports(c.map(([d, v, b]) => ({
        viewportId: d,
        element: document.getElementById(v),
        type: D.ORTHOGRAPHIC,
        defaultOptions: { orientation: b, background: [0, 0, 0] }
      })));
      const s = await W(p, { imageIds: o });
      await X(a, [{ volumeId: p }], c.map(([d]) => d)), s.load(), se(), c.forEach(([d, v]) => {
        const b = a.getViewport(d);
        b.resetCamera(), ie(d, b, document.getElementById(v));
      }), a.renderViewports(c.map(([d]) => d)), document.getElementById("mpr-loading").hidden = !0, R(c[0][0]), $("wl");
      const l = Number(document.getElementById("window-center")?.value || r.instancias[0]?.window_center), g = Number(document.getElementById("window-width")?.value || r.instancias[0]?.window_width);
      x(l, g);
    } catch (e) {
      O = !1, console.error("Loreto One MPR:", e), N(`No fue posible crear la reconstrucción: ${e.message}`, !0);
    }
  }
}
function le() {
  const e = document.getElementById("mpr-grid"), t = document.getElementById("viewer-stage"), n = document.getElementById("activar-mpr");
  i = !i, i || f(), e.hidden = !i, t.hidden = i, n.classList.toggle("active", i), n.textContent = i ? "Vista convencional" : "MPR 3 planos", document.querySelector(".viewer-shell")?.classList.toggle("mpr-active", i), i && ce().then(() => {
    a?.resize(!0, !1), a?.renderViewports(c.map(([r]) => r));
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
      const n = S(t, p, !1), r = Number(e.currentTarget.value) - 1;
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
  i && c.forEach(([e]) => {
    const t = a.getViewport(e);
    t.resetCamera(), t.resetProperties?.(), t.render();
  });
});
document.getElementById("borrar-mediciones")?.addEventListener("click", () => {
  if (!i) return;
  ne.removeAllAnnotations(), a?.renderViewports(c.map(([t]) => t));
  const e = document.getElementById("measurement-result");
  e && (e.textContent = "MPR · Mediciones eliminadas.");
});
document.getElementById("rotar")?.addEventListener("click", () => {
  if (!i) return;
  const e = m(), t = e?.getCamera?.();
  if (!t?.viewPlaneNormal || !t?.viewUp) return;
  const [n, r, o] = t.viewPlaneNormal, [s, l, g] = t.viewUp, d = [r * g - o * l, o * s - n * g, n * l - r * s];
  e.setCamera({ viewUp: d }), e.render();
});
document.getElementById("invertir")?.addEventListener("click", () => {
  if (!i) return;
  const e = m(), t = !B.has(w);
  e.setProperties({ invert: t }), t ? B.add(w) : B.delete(w), e.render();
});
document.querySelectorAll(".preset").forEach((e) => {
  e.addEventListener("click", () => x(Number(e.dataset.wc), Number(e.dataset.ww)));
});
document.getElementById("aplicar-ventana")?.addEventListener("click", () => {
  x(Number(document.getElementById("window-center").value), Number(document.getElementById("window-width").value));
});
window.addEventListener("resize", () => {
  !i || !a || (a.resize(!0, !1), a.renderViewports(c.map(([e]) => e)));
});
