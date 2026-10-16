import { O as B, C as L, d as Z, A as H, L as K, Z as W, W as j, P as X, i as ie, a as se, b as le, R as ce, V as Y, f as M, g as V, e as de, t as ue, k as me, M as pe, h as N, j as ge, c as fe, s as Ee } from "./chunks/VideoRedactionTool-BdY107HU.js";
const x = "LORETO_PUBLIC_ENGINE", s = "LORETO_PUBLIC_STACK", O = "LORETO_PUBLIC_STACK_TOOLS", C = "LORETO_PUBLIC_MPR_TOOLS", c = [
  ["LORETO_PUBLIC_AXIAL", "public-axial", B.AXIAL],
  ["LORETO_PUBLIC_CORONAL", "public-coronal", B.CORONAL],
  ["LORETO_PUBLIC_SAGITAL", "public-sagital", B.SAGITTAL]
], v = {
  pan: X.toolName,
  wl: j.toolName,
  zoom: W.toolName,
  length: K.toolName,
  angle: H.toolName,
  roi: Z.toolName,
  crosshairs: L.toolName
};
let a, w, J = 0, i = !1, R = null, Q = s, d = null, p = null, g, u, h = null, U = !1;
const G = document.getElementById("public-dicom-viewer"), S = document.getElementById("public-status"), ee = document.getElementById("public-slice-slider"), be = document.getElementById("public-counter"), te = document.getElementById("public-mpr-slice-slider"), we = document.getElementById("public-mpr-counter");
function he(e) {
  return new URL(e, window.location.origin).href;
}
function l(e, t = !1) {
  S && (S.textContent = e, S.classList.toggle("error", t));
}
function f() {
  return w?.series?.[J];
}
function ne(e) {
  return e.instancias.map((t) => `wadouri:${he(t.dicom_url)}`);
}
function m() {
  return a?.getViewport(Q);
}
function A() {
  return i ? c.map(([e]) => a.getViewport(e)).filter(Boolean) : [a.getViewport(s)].filter(Boolean);
}
function $() {
  A().forEach((e) => e.render());
}
function Le() {
  [
    X,
    j,
    W,
    K,
    H,
    Z,
    L
  ].forEach((e) => {
    try {
      de(e);
    } catch (t) {
      if (!String(t).toLowerCase().includes("already")) throw t;
    }
  });
}
function z(e, t = !1) {
  Object.entries(v).forEach(([n, r]) => {
    n === "crosshairs" && !t || e.hasTool?.(r) || (n === "crosshairs" ? e.addTool(r, {
      configuration: {
        getReferenceLineColor: (o) => ({
          LORETO_PUBLIC_AXIAL: "rgb(239,68,68)",
          LORETO_PUBLIC_CORONAL: "rgb(34,197,94)",
          LORETO_PUBLIC_SAGITAL: "rgb(59,130,246)"
        })[o] || "rgb(34,211,238)",
        getReferenceLineControllable: () => !0,
        getReferenceLineDraggableRotatable: () => !0,
        getReferenceLineSlabThicknessControlsOn: () => !1
      }
    }) : e.addTool(r));
  });
}
function D(e) {
  ue.setToolGroupToolStyles(e, {
    global: {
      color: "rgb(34,211,238)",
      colorHighlighted: "rgb(250,204,21)",
      colorSelected: "rgb(255,255,255)",
      lineWidth: "2",
      textBoxColor: "rgb(255,255,255)",
      textBoxBackground: "rgba(0,0,0,0.86)",
      textBoxLinkColor: "rgb(34,211,238)",
      textBoxShadow: !0,
      textBoxFontSize: "14px",
      textBoxFontFamily: "Arial, sans-serif"
    }
  });
}
function q(e) {
  e && Object.values(v).forEach((t) => {
    if (e.hasTool?.(t))
      try {
        e.setToolDisabled(t);
      } catch (n) {
        console.debug("No fue posible desactivar", t, n);
      }
  });
}
function I(e) {
  if (!Object.hasOwn(v, e)) return;
  if (e === "crosshairs" && !i) {
    l("Las cruces se utilizan dentro de MPR 3 planos.");
    return;
  }
  const t = d === e;
  if (q(g), q(u), d = t ? null : e, !t) {
    const n = v[e];
    [g, u].forEach((r) => {
      r?.hasTool?.(n) && (r.setToolEnabled(n), r.setToolActive(n, {
        bindings: [{ mouseButton: pe.Primary }]
      }));
    });
  }
  if (i && e !== "crosshairs" && u?.hasTool?.(L.toolName))
    try {
      u.setToolEnabled(L.toolName);
    } catch (n) {
      console.debug("Cruces MPR enlazadas:", n);
    }
  document.querySelectorAll("[data-public-tool]").forEach((n) => {
    const r = !t && n.dataset.publicTool === e;
    n.classList.toggle("active", r), n.setAttribute("aria-pressed", String(r));
  }), l(t ? "Herramienta desactivada. Usa la rueda o la barra vertical para navegar." : `Herramienta activa: ${document.querySelector(`[data-public-tool="${e}"]`)?.textContent.trim() || e}.`);
}
function y(e) {
  Q = e, document.querySelectorAll(".public-viewport").forEach((t) => {
    t.classList.toggle("selected", t.dataset.viewportId === e);
  }), re();
}
function E(e) {
  const t = m();
  !t || !e || (i ? (N(t, { delta: e, volumeId: p, scrollSlabs: !0 }), a.renderViewports(c.map(([n]) => n))) : (N(t, { delta: e }), t.render()), window.requestAnimationFrame(() => {
    i && a.renderViewports(c.map(([n]) => n)), re();
  }));
}
function P() {
  const e = m();
  if (!e) return null;
  if (i) {
    const t = ge(e, p, !1);
    return { index: t.currentStepIndex, count: t.numScrollSteps + 1 };
  }
  return {
    index: e.getCurrentImageIdIndex?.() ?? 0,
    count: e.getNumberOfSlices?.() ?? f()?.instancias.length ?? 1
  };
}
function re() {
  try {
    const e = P();
    if (!e || !Number.isFinite(e.index) || !Number.isFinite(e.count)) return;
    [ee, te].filter(Boolean).forEach((t) => {
      t.max = String(Math.max(1, e.count)), t.value = String(e.index + 1);
    }), [be, we].filter(Boolean).forEach((t) => {
      t.textContent = `${e.index + 1}/${e.count}`;
    });
  } catch (e) {
    console.debug("Contador DICOM:", e);
  }
}
function oe(e, t) {
  const n = () => y(t);
  e.addEventListener("pointerenter", n, !0), e.addEventListener("pointerdown", n, !0), e.addEventListener("wheel", (r) => {
    if (r.preventDefault(), r.stopPropagation(), n(), r.ctrlKey) {
      const o = m(), b = o.getZoom() * (r.deltaY < 0 ? 1.12 : 0.89);
      o.setZoom(Math.max(0.2, Math.min(12, b))), o.render();
    } else
      E(r.deltaY > 0 ? 1 : -1);
  }, { passive: !1 }), e.addEventListener("dblclick", () => {
    const r = a.getViewport(t);
    r.resetCamera(), r.render();
  });
}
async function F(e) {
  T(), J = e, R = null, document.querySelectorAll("[data-series-index]").forEach((n) => {
    n.classList.toggle("active", Number(n.dataset.seriesIndex) === e);
  }), i && await ae(!1);
  const t = a.getViewport(s);
  await t.setStack(ne(f())), t.resetCamera(), t.render(), y(s), document.getElementById("public-mpr-toggle").disabled = !f().apta_para_volumen, l(f().apta_para_volumen ? "Serie cargada. MPR disponible." : "Serie cargada. Esta serie no contiene geometría suficiente para MPR.");
}
async function ve() {
  const e = f();
  if (!e?.apta_para_volumen) throw new Error("Esta serie no es apta para reconstrucción multiplanar.");
  if (R === e.id) return;
  U || (c.forEach(([n, r, o]) => {
    a.enableElement({
      viewportId: n,
      element: document.getElementById(r),
      type: Y.ORTHOGRAPHIC,
      defaultOptions: { orientation: o, background: [0, 0, 0] }
    }), u.addViewport(n, x), oe(document.getElementById(r), n);
  }), U = !0), p = `cornerstoneStreamingImageVolume:public-${e.id}`;
  const t = await fe(p, {
    imageIds: ne(e)
  });
  await Ee(
    a,
    [{ volumeId: p }],
    c.map(([n]) => n)
  ), t.load(), c.forEach(([n]) => a.getViewport(n).resetCamera()), R = e.id;
}
async function ae(e) {
  const t = typeof e == "boolean" ? e : !i;
  if (t === i) return;
  const n = document.getElementById("public-mpr-toggle");
  if (t) {
    l("Preparando reconstrucción multiplanar…"), document.getElementById("public-stack-stage").hidden = !0, document.getElementById("public-mpr-grid").hidden = !1;
    try {
      if (await ve(), i = !0, n.textContent = "Vista axial original", n.classList.add("active"), document.querySelector('[data-public-tool="crosshairs"]').disabled = !1, a.resize(!0, !1), a.renderViewports(c.map(([r]) => r)), y(c[0][0]), d) {
        const r = d;
        d = null, I(r);
      }
      l("MPR enlazado activo. La rueda, barra, botones y cine actualizan la referencia en los tres planos.");
    } catch (r) {
      document.getElementById("public-stack-stage").hidden = !1, document.getElementById("public-mpr-grid").hidden = !0, l(`No fue posible crear MPR: ${r.message}`, !0);
    }
  } else
    i = !1, document.getElementById("public-stack-stage").hidden = !1, document.getElementById("public-mpr-grid").hidden = !0, n.textContent = "MPR 3 planos", n.classList.remove("active"), document.querySelector('[data-public-tool="crosshairs"]').disabled = !0, d === "crosshairs" && (d = null), a.resize(!0, !1), a.getViewport(s).render(), y(s), I("pan");
}
function Ie(e, t) {
  const n = { lower: e - t / 2, upper: e + t / 2 };
  A().forEach((r) => {
    r.setProperties({ voiRange: n }), r.render();
  });
}
function T() {
  h && window.clearTimeout(h), h = null;
}
function ye() {
  T();
  const e = () => {
    let t;
    try {
      t = P();
    } catch {
      t = null;
    }
    if (!t) return;
    E(t.index >= t.count - 1 ? -(t.count - 1) : 1);
    const n = Math.max(1, Number(document.getElementById("public-fps").value || 5));
    h = window.setTimeout(() => requestAnimationFrame(e), 1e3 / n);
  };
  e();
}
function Te() {
  document.querySelectorAll("[data-public-tool]").forEach((e) => {
    e.addEventListener("click", () => I(e.dataset.publicTool));
  }), document.querySelectorAll("[data-window]").forEach((e) => {
    e.addEventListener("click", () => {
      const [t, n] = e.dataset.window.split(",").map(Number);
      Ie(t, n);
    });
  }), document.getElementById("public-mpr-toggle").addEventListener("click", () => ae()), document.getElementById("public-zoom-plus").addEventListener("click", () => {
    const e = m();
    e.setZoom(Math.min(12, e.getZoom() * 1.2)), e.render();
  }), document.getElementById("public-zoom-minus").addEventListener("click", () => {
    const e = m();
    e.setZoom(Math.max(0.2, e.getZoom() / 1.2)), e.render();
  }), document.getElementById("public-invert").addEventListener("click", () => {
    const e = m(), t = e.getProperties?.() || {};
    e.setProperties({ invert: !t.invert }), e.render();
  }), document.getElementById("public-rotate").addEventListener("click", () => {
    const e = m(), t = e.getCamera?.();
    if (!t?.viewPlaneNormal || !t?.viewUp) return;
    const [n, r, o] = t.viewPlaneNormal, [b, _, k] = t.viewUp;
    e.setCamera({
      viewUp: [r * k - o * _, o * b - n * k, n * _ - r * b]
    }), e.render();
  }), document.getElementById("public-reset").addEventListener("click", () => {
    A().forEach((e) => {
      e.resetCamera(), e.resetProperties?.(), e.render();
    });
  }), document.getElementById("public-clear").addEventListener("click", () => {
    me.removeAllAnnotations(), $(), l("Mediciones eliminadas.");
  }), document.getElementById("public-prev").addEventListener("click", () => E(-1)), document.getElementById("public-next").addEventListener("click", () => E(1)), document.getElementById("public-cine").addEventListener("click", ye), document.getElementById("public-pause").addEventListener("click", T), [ee, te].filter(Boolean).forEach((e) => {
    e.addEventListener("pointerdown", (t) => t.stopPropagation()), e.addEventListener("touchmove", (t) => {
      t.preventDefault(), t.stopPropagation();
    }, { passive: !1 }), e.addEventListener("input", () => {
      T();
      const t = Number(e.value) - 1, n = P();
      E(t - n.index);
    });
  }), window.addEventListener("resize", () => {
    a?.resize(!0, !1), $();
  });
}
async function Be() {
  if (G)
    try {
      l("Preparando visor DICOM…"), await ie(), await se({
        maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2))
      }), await le(), Le();
      const e = await fetch(G.dataset.manifestUrl, { credentials: "same-origin" });
      if (!e.ok) throw new Error(`El manifiesto respondió ${e.status}.`);
      if (w = await e.json(), !w.series?.length) throw new Error("El estudio no contiene series DICOM disponibles.");
      a = new ce(x), a.enableElement({
        viewportId: s,
        element: document.getElementById("public-stack"),
        type: Y.STACK,
        defaultOptions: { background: [0, 0, 0] }
      }), oe(document.getElementById("public-stack"), s), g = M(O) || V(O), u = M(C) || V(C), z(g, !1), z(u, !0), g.addViewport(s, x), D(O), D(C);
      const t = document.getElementById("public-series-list");
      w.series.forEach((n, r) => {
        const o = document.createElement("button");
        o.type = "button", o.className = "public-series-card", o.dataset.seriesIndex = String(r), o.innerHTML = `<strong>${n.modalidad || "DICOM"}</strong><span>${n.descripcion || "Serie sin descripción"}</span><small>${n.cantidad_instancias} imágenes${n.apta_para_volumen ? " · MPR" : ""}</small>`, o.addEventListener("click", () => F(r)), t.appendChild(o);
      }), Te(), await F(0), I("pan");
    } catch (e) {
      console.error("Loreto One visor externo:", e), l(`No fue posible iniciar el visor: ${e.message}`, !0);
    }
}
Be();
