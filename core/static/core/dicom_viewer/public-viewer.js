import { O as T, C as F, d as Z, A as H, L as K, Z as W, W as j, P as X, i as ae, a as se, b as le, R as ce, V as Y, f as k, g as M, e as de, t as ue, k as me, M as pe, h as V, j as ge, c as fe, s as Ee } from "./chunks/VideoRedactionTool-BdY107HU.js";
const S = "LORETO_PUBLIC_ENGINE", s = "LORETO_PUBLIC_STACK", B = "LORETO_PUBLIC_STACK_TOOLS", O = "LORETO_PUBLIC_MPR_TOOLS", u = [
  ["LORETO_PUBLIC_AXIAL", "public-axial", T.AXIAL],
  ["LORETO_PUBLIC_CORONAL", "public-coronal", T.CORONAL],
  ["LORETO_PUBLIC_SAGITAL", "public-sagital", T.SAGITTAL]
], L = {
  pan: X.toolName,
  wl: j.toolName,
  zoom: W.toolName,
  length: K.toolName,
  angle: H.toolName,
  roi: Z.toolName,
  crosshairs: F.toolName
};
let i, w, J = 0, a = !1, x = null, Q = s, c = null, m = null, p, E, v = null, N = !1;
const U = document.getElementById("public-dicom-viewer"), C = document.getElementById("public-status"), ee = document.getElementById("public-slice-slider"), be = document.getElementById("public-counter"), te = document.getElementById("public-mpr-slice-slider"), we = document.getElementById("public-mpr-counter");
function ve(e) {
  return new URL(e, window.location.origin).href;
}
function l(e, t = !1) {
  C && (C.textContent = e, C.classList.toggle("error", t));
}
function g() {
  return w?.series?.[J];
}
function ne(e) {
  return e.instancias.map((t) => `wadouri:${ve(t.dicom_url)}`);
}
function d() {
  return i?.getViewport(Q);
}
function A() {
  return a ? u.map(([e]) => i.getViewport(e)).filter(Boolean) : [i.getViewport(s)].filter(Boolean);
}
function G() {
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
    F
  ].forEach((e) => {
    try {
      de(e);
    } catch (t) {
      if (!String(t).toLowerCase().includes("already")) throw t;
    }
  });
}
function $(e, t = !1) {
  Object.entries(L).forEach(([n, r]) => {
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
function z(e) {
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
function D(e) {
  e && Object.values(L).forEach((t) => {
    if (e.hasTool?.(t))
      try {
        e.setToolDisabled(t);
      } catch (n) {
        console.debug("No fue posible desactivar", t, n);
      }
  });
}
function h(e) {
  if (!Object.hasOwn(L, e)) return;
  if (e === "crosshairs" && !a) {
    l("Las cruces se utilizan dentro de MPR 3 planos.");
    return;
  }
  const t = c === e;
  if (D(p), D(E), c = t ? null : e, !t) {
    const n = L[e];
    [p, E].forEach((r) => {
      r?.hasTool?.(n) && (r.setToolEnabled(n), r.setToolActive(n, {
        bindings: [{ mouseButton: pe.Primary }]
      }));
    });
  }
  document.querySelectorAll("[data-public-tool]").forEach((n) => {
    const r = !t && n.dataset.publicTool === e;
    n.classList.toggle("active", r), n.setAttribute("aria-pressed", String(r));
  }), l(t ? "Herramienta desactivada. Usa la rueda o la barra vertical para navegar." : `Herramienta activa: ${document.querySelector(`[data-public-tool="${e}"]`)?.textContent.trim() || e}.`);
}
function I(e) {
  Q = e, document.querySelectorAll(".public-viewport").forEach((t) => {
    t.classList.toggle("selected", t.dataset.viewportId === e);
  }), re();
}
function f(e) {
  const t = d();
  !t || !e || (a ? V(t, { delta: e, volumeId: m, scrollSlabs: !0 }) : V(t, { delta: e }), t.render(), window.requestAnimationFrame(re));
}
function R() {
  const e = d();
  if (!e) return null;
  if (a) {
    const t = ge(e, m, !1);
    return { index: t.currentStepIndex, count: t.numScrollSteps + 1 };
  }
  return {
    index: e.getCurrentImageIdIndex?.() ?? 0,
    count: e.getNumberOfSlices?.() ?? g()?.instancias.length ?? 1
  };
}
function re() {
  try {
    const e = R();
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
  const n = () => I(t);
  e.addEventListener("pointerenter", n, !0), e.addEventListener("pointerdown", n, !0), e.addEventListener("wheel", (r) => {
    if (r.preventDefault(), r.stopPropagation(), n(), r.ctrlKey) {
      const o = d(), b = o.getZoom() * (r.deltaY < 0 ? 1.12 : 0.89);
      o.setZoom(Math.max(0.2, Math.min(12, b))), o.render();
    } else
      f(r.deltaY > 0 ? 1 : -1);
  }, { passive: !1 }), e.addEventListener("dblclick", () => {
    const r = i.getViewport(t);
    r.resetCamera(), r.render();
  });
}
async function q(e) {
  y(), J = e, x = null, document.querySelectorAll("[data-series-index]").forEach((n) => {
    n.classList.toggle("active", Number(n.dataset.seriesIndex) === e);
  }), a && await ie(!1);
  const t = i.getViewport(s);
  await t.setStack(ne(g())), t.resetCamera(), t.render(), I(s), document.getElementById("public-mpr-toggle").disabled = !g().apta_para_volumen, l(g().apta_para_volumen ? "Serie cargada. MPR disponible." : "Serie cargada. Esta serie no contiene geometría suficiente para MPR.");
}
async function he() {
  const e = g();
  if (!e?.apta_para_volumen) throw new Error("Esta serie no es apta para reconstrucción multiplanar.");
  if (x === e.id) return;
  N || (u.forEach(([n, r, o]) => {
    i.enableElement({
      viewportId: n,
      element: document.getElementById(r),
      type: Y.ORTHOGRAPHIC,
      defaultOptions: { orientation: o, background: [0, 0, 0] }
    }), E.addViewport(n, S), oe(document.getElementById(r), n);
  }), N = !0), m = `cornerstoneStreamingImageVolume:public-${e.id}`;
  const t = await fe(m, {
    imageIds: ne(e)
  });
  await Ee(
    i,
    [{ volumeId: m }],
    u.map(([n]) => n)
  ), t.load(), u.forEach(([n]) => i.getViewport(n).resetCamera()), x = e.id;
}
async function ie(e) {
  const t = typeof e == "boolean" ? e : !a;
  if (t === a) return;
  const n = document.getElementById("public-mpr-toggle");
  if (t) {
    l("Preparando reconstrucción multiplanar…"), document.getElementById("public-stack-stage").hidden = !0, document.getElementById("public-mpr-grid").hidden = !1;
    try {
      if (await he(), a = !0, n.textContent = "Vista axial original", n.classList.add("active"), document.querySelector('[data-public-tool="crosshairs"]').disabled = !1, i.resize(!0, !1), i.renderViewports(u.map(([r]) => r)), I(u[0][0]), c) {
        const r = c;
        c = null, h(r);
      }
      l("MPR activo. Selecciona un plano y utiliza sus herramientas.");
    } catch (r) {
      document.getElementById("public-stack-stage").hidden = !1, document.getElementById("public-mpr-grid").hidden = !0, l(`No fue posible crear MPR: ${r.message}`, !0);
    }
  } else
    a = !1, document.getElementById("public-stack-stage").hidden = !1, document.getElementById("public-mpr-grid").hidden = !0, n.textContent = "MPR 3 planos", n.classList.remove("active"), document.querySelector('[data-public-tool="crosshairs"]').disabled = !0, c === "crosshairs" && (c = null), i.resize(!0, !1), i.getViewport(s).render(), I(s), h("pan");
}
function Ie(e, t) {
  const n = { lower: e - t / 2, upper: e + t / 2 };
  A().forEach((r) => {
    r.setProperties({ voiRange: n }), r.render();
  });
}
function y() {
  v && window.clearTimeout(v), v = null;
}
function ye() {
  y();
  const e = () => {
    let t;
    try {
      t = R();
    } catch {
      t = null;
    }
    if (!t) return;
    f(t.index >= t.count - 1 ? -(t.count - 1) : 1);
    const n = Math.max(1, Number(document.getElementById("public-fps").value || 5));
    v = window.setTimeout(() => requestAnimationFrame(e), 1e3 / n);
  };
  e();
}
function Te() {
  document.querySelectorAll("[data-public-tool]").forEach((e) => {
    e.addEventListener("click", () => h(e.dataset.publicTool));
  }), document.querySelectorAll("[data-window]").forEach((e) => {
    e.addEventListener("click", () => {
      const [t, n] = e.dataset.window.split(",").map(Number);
      Ie(t, n);
    });
  }), document.getElementById("public-mpr-toggle").addEventListener("click", () => ie()), document.getElementById("public-zoom-plus").addEventListener("click", () => {
    const e = d();
    e.setZoom(Math.min(12, e.getZoom() * 1.2)), e.render();
  }), document.getElementById("public-zoom-minus").addEventListener("click", () => {
    const e = d();
    e.setZoom(Math.max(0.2, e.getZoom() / 1.2)), e.render();
  }), document.getElementById("public-invert").addEventListener("click", () => {
    const e = d(), t = e.getProperties?.() || {};
    e.setProperties({ invert: !t.invert }), e.render();
  }), document.getElementById("public-rotate").addEventListener("click", () => {
    const e = d(), t = e.getCamera?.();
    if (!t?.viewPlaneNormal || !t?.viewUp) return;
    const [n, r, o] = t.viewPlaneNormal, [b, _, P] = t.viewUp;
    e.setCamera({
      viewUp: [r * P - o * _, o * b - n * P, n * _ - r * b]
    }), e.render();
  }), document.getElementById("public-reset").addEventListener("click", () => {
    A().forEach((e) => {
      e.resetCamera(), e.resetProperties?.(), e.render();
    });
  }), document.getElementById("public-clear").addEventListener("click", () => {
    me.removeAllAnnotations(), G(), l("Mediciones eliminadas.");
  }), document.getElementById("public-prev").addEventListener("click", () => f(-1)), document.getElementById("public-next").addEventListener("click", () => f(1)), document.getElementById("public-cine").addEventListener("click", ye), document.getElementById("public-pause").addEventListener("click", y), [ee, te].filter(Boolean).forEach((e) => {
    e.addEventListener("pointerdown", (t) => t.stopPropagation()), e.addEventListener("touchmove", (t) => {
      t.preventDefault(), t.stopPropagation();
    }, { passive: !1 }), e.addEventListener("input", () => {
      y();
      const t = Number(e.value) - 1, n = R();
      f(t - n.index);
    });
  }), window.addEventListener("resize", () => {
    i?.resize(!0, !1), G();
  });
}
async function Be() {
  if (U)
    try {
      l("Preparando visor DICOM…"), await ae(), await se({
        maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2))
      }), await le(), Le();
      const e = await fetch(U.dataset.manifestUrl, { credentials: "same-origin" });
      if (!e.ok) throw new Error(`El manifiesto respondió ${e.status}.`);
      if (w = await e.json(), !w.series?.length) throw new Error("El estudio no contiene series DICOM disponibles.");
      i = new ce(S), i.enableElement({
        viewportId: s,
        element: document.getElementById("public-stack"),
        type: Y.STACK,
        defaultOptions: { background: [0, 0, 0] }
      }), oe(document.getElementById("public-stack"), s), p = k(B) || M(B), E = k(O) || M(O), $(p, !1), $(E, !0), p.addViewport(s, S), z(B), z(O);
      const t = document.getElementById("public-series-list");
      w.series.forEach((n, r) => {
        const o = document.createElement("button");
        o.type = "button", o.className = "public-series-card", o.dataset.seriesIndex = String(r), o.innerHTML = `<strong>${n.modalidad || "DICOM"}</strong><span>${n.descripcion || "Serie sin descripción"}</span><small>${n.cantidad_instancias} imágenes${n.apta_para_volumen ? " · MPR" : ""}</small>`, o.addEventListener("click", () => q(r)), t.appendChild(o);
      }), Te(), await q(0), h("pan");
    } catch (e) {
      console.error("Loreto One visor externo:", e), l(`No fue posible iniciar el visor: ${e.message}`, !0);
    }
}
Be();
