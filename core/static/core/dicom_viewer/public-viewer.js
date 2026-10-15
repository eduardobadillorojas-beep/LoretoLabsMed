import { O as S, C as y, d as K, A as W, L as j, Z as X, W as Y, P as J, i as le, a as ce, b as de, R as ue, V as Q, f as N, g as U, e as me, E as pe, t as fe, k as ge, M as Ee, h as G, j as be, c as we, s as ve } from "./chunks/VideoRedactionTool-PF0Cw2kQ.js";
const _ = "LORETO_PUBLIC_ENGINE", l = "LORETO_PUBLIC_STACK", x = "LORETO_PUBLIC_STACK_TOOLS", A = "LORETO_PUBLIC_MPR_TOOLS", p = [
  ["LORETO_PUBLIC_AXIAL", "public-axial", S.AXIAL],
  ["LORETO_PUBLIC_CORONAL", "public-coronal", S.CORONAL],
  ["LORETO_PUBLIC_SAGITAL", "public-sagital", S.SAGITTAL]
], T = {
  pan: J.toolName,
  wl: Y.toolName,
  zoom: X.toolName,
  length: j.toolName,
  angle: W.toolName,
  roi: K.toolName,
  crosshairs: y.toolName
};
let a, h, ee = 0, s = !1, P = null, te = l, d = null, g = null, E, u, I = null, $ = !1, L = null;
const z = document.getElementById("public-dicom-viewer"), R = document.getElementById("public-status"), ne = document.getElementById("public-slice-slider"), Le = document.getElementById("public-counter"), re = document.getElementById("public-mpr-slice-slider"), he = document.getElementById("public-mpr-counter");
function Ie(e) {
  return new URL(e, window.location.origin).href;
}
function c(e, t = !1) {
  R && (R.textContent = e, R.classList.toggle("error", t));
}
function b() {
  return h?.series?.[ee];
}
function oe(e) {
  return e.instancias.map((t) => `wadouri:${Ie(t.dicom_url)}`);
}
function m() {
  return a?.getViewport(te);
}
function k() {
  return s ? p.map(([e]) => a.getViewport(e)).filter(Boolean) : [a.getViewport(l)].filter(Boolean);
}
function D() {
  k().forEach((e) => e.render());
}
function ae() {
  !s || !a || (L && window.cancelAnimationFrame(L), L = window.requestAnimationFrame(() => {
    L = null, a.renderViewports(p.map(([e]) => e)), V();
  }));
}
function ye() {
  [
    J,
    Y,
    X,
    j,
    W,
    K,
    y
  ].forEach((e) => {
    try {
      me(e);
    } catch (t) {
      if (!String(t).toLowerCase().includes("already")) throw t;
    }
  });
}
function F(e, t = !1) {
  Object.entries(T).forEach(([n, r]) => {
    n === "crosshairs" && !t || e.hasTool?.(r) || (n === "crosshairs" ? e.addTool(r, {
      configuration: {
        getReferenceLineColor: (i) => ({
          LORETO_PUBLIC_AXIAL: "rgb(239,68,68)",
          LORETO_PUBLIC_CORONAL: "rgb(34,197,94)",
          LORETO_PUBLIC_SAGITAL: "rgb(59,130,246)"
        })[i] || "rgb(34,211,238)",
        getReferenceLineControllable: () => !0,
        getReferenceLineDraggableRotatable: () => !0,
        getReferenceLineSlabThicknessControlsOn: () => !1
      }
    }) : e.addTool(r));
  });
}
function q(e) {
  fe.setToolGroupToolStyles(e, {
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
function Z(e) {
  e && Object.values(T).forEach((t) => {
    if (e.hasTool?.(t))
      try {
        e.setToolDisabled(t);
      } catch (n) {
        console.debug("No fue posible desactivar", t, n);
      }
  });
}
function B(e) {
  if (!Object.hasOwn(T, e)) return;
  if (e === "crosshairs" && !s) {
    c("Las cruces se utilizan dentro de MPR 3 planos.");
    return;
  }
  const t = d === e;
  if (Z(E), Z(u), d = t ? null : e, !t) {
    const n = T[e];
    [E, u].forEach((r) => {
      r?.hasTool?.(n) && (r.setToolEnabled(n), r.setToolActive(n, {
        bindings: [{ mouseButton: Ee.Primary }]
      }));
    });
  }
  if (s && e !== "crosshairs" && u?.hasTool?.(y.toolName))
    try {
      u.setToolEnabled(y.toolName);
    } catch (n) {
      console.debug("Cruces MPR enlazadas:", n);
    }
  document.querySelectorAll("[data-public-tool]").forEach((n) => {
    const r = !t && n.dataset.publicTool === e;
    n.classList.toggle("active", r), n.setAttribute("aria-pressed", String(r));
  }), c(t ? "Herramienta desactivada. Usa la rueda o la barra vertical para navegar." : `Herramienta activa: ${document.querySelector(`[data-public-tool="${e}"]`)?.textContent.trim() || e}.`);
}
function O(e) {
  te = e, document.querySelectorAll(".public-viewport").forEach((t) => {
    t.classList.toggle("selected", t.dataset.viewportId === e);
  }), V();
}
function w(e) {
  const t = m();
  !t || !e || (s ? (G(t, { delta: e, volumeId: g, scrollSlabs: !0 }), ae()) : (G(t, { delta: e }), t.render()), s || window.requestAnimationFrame(V));
}
function M() {
  const e = m();
  if (!e) return null;
  if (s) {
    const t = be(e, g, !1);
    return { index: t.currentStepIndex, count: t.numScrollSteps + 1 };
  }
  return {
    index: e.getCurrentImageIdIndex?.() ?? 0,
    count: e.getNumberOfSlices?.() ?? b()?.instancias.length ?? 1
  };
}
function V() {
  try {
    const e = M();
    if (!e || !Number.isFinite(e.index) || !Number.isFinite(e.count)) return;
    [ne, re].filter(Boolean).forEach((t) => {
      t.max = String(Math.max(1, e.count)), t.value = String(e.index + 1);
    }), [Le, he].filter(Boolean).forEach((t) => {
      t.textContent = `${e.index + 1}/${e.count}`;
    });
  } catch (e) {
    console.debug("Contador DICOM:", e);
  }
}
function ie(e, t) {
  const n = () => O(t), r = e.closest?.(".public-viewport") || e.parentElement;
  new Set([e, r].filter(Boolean)).forEach((o) => {
    o.addEventListener("pointerenter", n, !0), o.addEventListener("pointerdown", n, !0), o.addEventListener("mousedown", n, !0), o.addEventListener("touchstart", n, { capture: !0, passive: !0 }), o.addEventListener("click", n, !0);
  }), e.addEventListener(pe.CAMERA_MODIFIED, () => {
    ae();
  }), e.addEventListener("wheel", (o) => {
    if (o.preventDefault(), o.stopPropagation(), n(), o.ctrlKey) {
      const f = m(), v = f.getZoom() * (o.deltaY < 0 ? 1.12 : 0.89);
      f.setZoom(Math.max(0.2, Math.min(12, v))), f.render();
    } else
      w(o.deltaY > 0 ? 1 : -1);
  }, { passive: !1 }), e.addEventListener("dblclick", () => {
    const o = a.getViewport(t);
    o.resetCamera(), o.render();
  });
}
async function H(e) {
  C(), ee = e, P = null, document.querySelectorAll("[data-series-index]").forEach((n) => {
    n.classList.toggle("active", Number(n.dataset.seriesIndex) === e);
  }), s && await se(!1);
  const t = a.getViewport(l);
  await t.setStack(oe(b())), t.resetCamera(), t.render(), O(l), document.getElementById("public-mpr-toggle").disabled = !b().apta_para_volumen, c(b().apta_para_volumen ? "Serie cargada. MPR disponible." : "Serie cargada. Esta serie no contiene geometría suficiente para MPR.");
}
async function Te() {
  const e = b();
  if (!e?.apta_para_volumen) throw new Error("Esta serie no es apta para reconstrucción multiplanar.");
  if (P === e.id) return;
  $ || (p.forEach(([n, r, i]) => {
    a.enableElement({
      viewportId: n,
      element: document.getElementById(r),
      type: Q.ORTHOGRAPHIC,
      defaultOptions: { orientation: i, background: [0, 0, 0] }
    }), u.addViewport(n, _), ie(document.getElementById(r), n);
  }), $ = !0), g = `cornerstoneStreamingImageVolume:public-${e.id}`;
  const t = await we(g, {
    imageIds: oe(e)
  });
  await ve(
    a,
    [{ volumeId: g }],
    p.map(([n]) => n)
  ), t.load(), p.forEach(([n]) => a.getViewport(n).resetCamera()), P = e.id;
}
async function se(e) {
  const t = typeof e == "boolean" ? e : !s;
  if (t === s) return;
  const n = document.getElementById("public-mpr-toggle");
  if (t) {
    c("Preparando reconstrucción multiplanar…"), document.getElementById("public-stack-stage").hidden = !0, document.getElementById("public-mpr-grid").hidden = !1;
    try {
      if (await Te(), s = !0, n.textContent = "Vista axial original", n.classList.add("active"), document.querySelector('[data-public-tool="crosshairs"]').disabled = !1, a.resize(!0, !1), a.renderViewports(p.map(([r]) => r)), O(p[0][0]), d) {
        const r = d;
        d = null, B(r);
      }
      c("MPR enlazado activo. La rueda, barra, botones y cine actualizan la referencia en los tres planos.");
    } catch (r) {
      document.getElementById("public-stack-stage").hidden = !1, document.getElementById("public-mpr-grid").hidden = !0, c(`No fue posible crear MPR: ${r.message}`, !0);
    }
  } else
    s = !1, document.getElementById("public-stack-stage").hidden = !1, document.getElementById("public-mpr-grid").hidden = !0, n.textContent = "MPR 3 planos", n.classList.remove("active"), document.querySelector('[data-public-tool="crosshairs"]').disabled = !0, d === "crosshairs" && (d = null), a.resize(!0, !1), a.getViewport(l).render(), O(l), B("pan");
}
function Be(e, t) {
  const n = { lower: e - t / 2, upper: e + t / 2 };
  k().forEach((r) => {
    r.setProperties({ voiRange: n }), r.render();
  });
}
function C() {
  I && window.clearTimeout(I), I = null;
}
function Oe() {
  C();
  const e = () => {
    let t;
    try {
      t = M();
    } catch {
      t = null;
    }
    if (!t) return;
    w(t.index >= t.count - 1 ? -(t.count - 1) : 1);
    const n = Math.max(1, Number(document.getElementById("public-fps").value || 5));
    I = window.setTimeout(() => requestAnimationFrame(e), 1e3 / n);
  };
  e();
}
function Ce() {
  document.querySelectorAll("[data-public-tool]").forEach((e) => {
    e.addEventListener("click", () => B(e.dataset.publicTool));
  }), document.querySelectorAll("[data-window]").forEach((e) => {
    e.addEventListener("click", () => {
      const [t, n] = e.dataset.window.split(",").map(Number);
      Be(t, n);
    });
  }), document.getElementById("public-mpr-toggle").addEventListener("click", () => se()), document.getElementById("public-zoom-plus").addEventListener("click", () => {
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
    const [n, r, i] = t.viewPlaneNormal, [o, f, v] = t.viewUp;
    e.setCamera({
      viewUp: [r * v - i * f, i * o - n * v, n * f - r * o]
    }), e.render();
  }), document.getElementById("public-reset").addEventListener("click", () => {
    k().forEach((e) => {
      e.resetCamera(), e.resetProperties?.(), e.render();
    });
  }), document.getElementById("public-clear").addEventListener("click", () => {
    ge.removeAllAnnotations(), D(), c("Mediciones eliminadas.");
  }), document.getElementById("public-prev").addEventListener("click", () => w(-1)), document.getElementById("public-next").addEventListener("click", () => w(1)), document.getElementById("public-cine").addEventListener("click", Oe), document.getElementById("public-pause").addEventListener("click", C), [ne, re].filter(Boolean).forEach((e) => {
    e.addEventListener("pointerdown", (t) => t.stopPropagation()), e.addEventListener("touchmove", (t) => {
      t.preventDefault(), t.stopPropagation();
    }, { passive: !1 }), e.addEventListener("input", () => {
      C();
      const t = Number(e.value) - 1, n = M();
      w(t - n.index);
    });
  }), window.addEventListener("resize", () => {
    a?.resize(!0, !1), D();
  });
}
async function Se() {
  if (z)
    try {
      c("Preparando visor DICOM…"), await le(), await ce({
        maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2))
      }), await de(), ye();
      const e = await fetch(z.dataset.manifestUrl, { credentials: "same-origin" });
      if (!e.ok) throw new Error(`El manifiesto respondió ${e.status}.`);
      if (h = await e.json(), !h.series?.length) throw new Error("El estudio no contiene series DICOM disponibles.");
      a = new ue(_), a.enableElement({
        viewportId: l,
        element: document.getElementById("public-stack"),
        type: Q.STACK,
        defaultOptions: { background: [0, 0, 0] }
      }), ie(document.getElementById("public-stack"), l), E = N(x) || U(x), u = N(A) || U(A), F(E, !1), F(u, !0), E.addViewport(l, _), q(x), q(A);
      const t = document.getElementById("public-series-list");
      h.series.forEach((n, r) => {
        const i = document.createElement("button");
        i.type = "button", i.className = "public-series-card", i.dataset.seriesIndex = String(r), i.innerHTML = `<strong>${n.modalidad || "DICOM"}</strong><span>${n.descripcion || "Serie sin descripción"}</span><small>${n.cantidad_instancias} imágenes${n.apta_para_volumen ? " · MPR" : ""}</small>`, i.addEventListener("click", () => H(r)), t.appendChild(i);
      }), Ce(), await H(0), B("pan");
    } catch (e) {
      console.error("Loreto One visor externo:", e), c(`No fue posible iniciar el visor: ${e.message}`, !0);
    }
}
Se();
