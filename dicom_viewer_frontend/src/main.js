import {
  Enums,
  RenderingEngine,
  init as coreInit,
  setVolumesForViewports,
  utilities,
  volumeLoader,
} from '@cornerstonejs/core';
import { init as dicomImageLoaderInit } from '@cornerstonejs/dicom-image-loader';

const VIEWPORTS = [
  ['LORETO_AXIAL', 'mpr-axial', Enums.OrientationAxis.AXIAL],
  ['LORETO_CORONAL', 'mpr-coronal', Enums.OrientationAxis.CORONAL],
  ['LORETO_SAGITAL', 'mpr-sagital', Enums.OrientationAxis.SAGITTAL],
];

let started = false;
let active = false;
let renderingEngine = null;
let volumeId = null;

function absoluteUrl(value) {
  return new URL(value, window.location.origin).href;
}

function message(text, isError = false) {
  const loading = document.getElementById('mpr-loading');
  if (!loading) return;
  loading.hidden = false;
  loading.textContent = text;
  loading.style.color = isError ? '#fecaca' : '#d8e9f3';
}

function currentSeries(manifest) {
  const currentOriginal = document.getElementById('descargar-original')?.href;
  return manifest.series.find(series =>
    series.instancias.some(instance => absoluteUrl(instance.dicom_url) === currentOriginal)
  ) || manifest.series.find(series => series.apta_para_volumen);
}

function configureInteractions(viewport, element) {
  element.addEventListener('wheel', event => {
    event.preventDefault();
    if (event.ctrlKey) {
      const current = viewport.getZoom();
      viewport.setZoom(Math.max(0.2, Math.min(12, current * (event.deltaY < 0 ? 1.12 : 0.89))));
    } else {
      utilities.scroll(viewport, {
        delta: event.deltaY > 0 ? 1 : -1,
        volumeId,
      });
    }
    viewport.render();
  }, { passive: false });

  element.addEventListener('dblclick', () => {
    viewport.resetCamera();
    viewport.render();
  });
}

function applyPreset(center, width) {
  if (!active || !renderingEngine || !Number.isFinite(center) || !Number.isFinite(width)) return;
  const voiRange = { lower: center - width / 2, upper: center + width / 2 };
  VIEWPORTS.forEach(([id]) => {
    const viewport = renderingEngine.getViewport(id);
    viewport.setProperties({ voiRange });
    viewport.render();
  });
}

async function startMpr() {
  if (started) return;
  started = true;
  message('Leyendo geometría y píxeles DICOM…');

  try {
    await coreInit();
    await dicomImageLoaderInit({ maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2)) });

    const root = document.querySelector('.dicom-wrap');
    const response = await fetch(root.dataset.manifestUrl, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`El manifiesto respondió ${response.status}.`);
    const manifest = await response.json();
    const series = currentSeries(manifest);
    if (!series) throw new Error('Este estudio no contiene una serie volumétrica compatible.');
    if (!series.apta_para_volumen) {
      throw new Error('La serie no contiene posición y orientación suficientes para MPR.');
    }
    if (series.instancias.length < 3) throw new Error('Se necesitan por lo menos tres cortes para reconstruir un volumen.');

    const imageIds = series.instancias.map(instance => `wadouri:${absoluteUrl(instance.dicom_url)}`);
    volumeId = `cornerstoneStreamingImageVolume:loreto-${manifest.estudio.id}-${series.id}`;
    renderingEngine = new RenderingEngine(`LORETO_ENGINE_${manifest.estudio.id}`);
    renderingEngine.setViewports(VIEWPORTS.map(([viewportId, elementId, orientation]) => ({
      viewportId,
      element: document.getElementById(elementId),
      type: Enums.ViewportType.ORTHOGRAPHIC,
      defaultOptions: { orientation, background: [0, 0, 0] },
    })));

    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    await setVolumesForViewports(renderingEngine, [{ volumeId }], VIEWPORTS.map(([id]) => id));
    volume.load();

    VIEWPORTS.forEach(([id, elementId]) => {
      const viewport = renderingEngine.getViewport(id);
      viewport.resetCamera();
      configureInteractions(viewport, document.getElementById(elementId));
    });
    renderingEngine.renderViewports(VIEWPORTS.map(([id]) => id));
    document.getElementById('mpr-loading').hidden = true;

    const center = Number(document.getElementById('window-center')?.value || series.instancias[0]?.window_center);
    const width = Number(document.getElementById('window-width')?.value || series.instancias[0]?.window_width);
    applyPreset(center, width);
  } catch (error) {
    started = false;
    console.error('Loreto One MPR:', error);
    message(`No fue posible crear la reconstrucción: ${error.message}`, true);
  }
}

function toggleMpr() {
  const grid = document.getElementById('mpr-grid');
  const stack = document.getElementById('viewer-stage');
  const button = document.getElementById('activar-mpr');
  active = !active;
  grid.hidden = !active;
  stack.hidden = active;
  button.classList.toggle('active', active);
  button.textContent = active ? 'Vista convencional' : 'MPR 3 planos';
  if (active) {
    startMpr().then(() => {
      renderingEngine?.resize(true, false);
      renderingEngine?.renderViewports(VIEWPORTS.map(([id]) => id));
    });
  }
}

document.getElementById('activar-mpr')?.addEventListener('click', toggleMpr);
document.querySelectorAll('.preset').forEach(button => {
  button.addEventListener('click', () => applyPreset(Number(button.dataset.wc), Number(button.dataset.ww)));
});
document.getElementById('aplicar-ventana')?.addEventListener('click', () => {
  applyPreset(Number(document.getElementById('window-center').value), Number(document.getElementById('window-width').value));
});
window.addEventListener('resize', () => {
  if (!active || !renderingEngine) return;
  renderingEngine.resize(true, false);
  renderingEngine.renderViewports(VIEWPORTS.map(([id]) => id));
});

