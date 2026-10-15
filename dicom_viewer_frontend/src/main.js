import {
  Enums,
  RenderingEngine,
  init as coreInit,
  setVolumesForViewports,
  utilities,
  volumeLoader,
} from '@cornerstonejs/core';
import { init as dicomImageLoaderInit } from '@cornerstonejs/dicom-image-loader';
import {
  addTool,
  AngleTool,
  CrosshairsTool,
  Enums as ToolsEnums,
  LengthTool,
  PanTool,
  RectangleROITool,
  ToolGroupManager,
  WindowLevelTool,
  ZoomTool,
  annotation,
  init as toolsInit,
} from '@cornerstonejs/tools';

const VIEWPORTS = [
  ['LORETO_AXIAL', 'mpr-axial', Enums.OrientationAxis.AXIAL],
  ['LORETO_CORONAL', 'mpr-coronal', Enums.OrientationAxis.CORONAL],
  ['LORETO_SAGITAL', 'mpr-sagital', Enums.OrientationAxis.SAGITTAL],
];

let started = false;
let active = false;
let renderingEngine = null;
let volumeId = null;
let activeTool = null;
let activeViewportId = VIEWPORTS[0][0];
const invertedViewports = new Set();
let mprCineTimer = null;
let mprCinePlaying = false;
let toolGroup = null;
const renderingEngineId = 'LORETO_MPR_ENGINE';
const toolGroupId = 'LORETO_MPR_TOOLS';

const TOOL_NAMES = {
  pan: PanTool.toolName,
  wl: WindowLevelTool.toolName,
  zoom: ZoomTool.toolName,
  distancia: LengthTool.toolName,
  angulo: AngleTool.toolName,
  roi: RectangleROITool.toolName,
  cruces: CrosshairsTool.toolName,
};

const PLANE_DATA = {
  LORETO_AXIAL: { label: 'AXIAL', top: 'S', bottom: 'I' },
  LORETO_CORONAL: { label: 'CORONAL', top: 'S', bottom: 'I' },
  LORETO_SAGITAL: { label: 'SAGITAL', top: 'S', bottom: 'I' },
};

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

function selectViewport(viewportId) {
  activeViewportId = viewportId;
  VIEWPORTS.forEach(([id, elementId]) => {
    document.getElementById(elementId)?.parentElement?.classList.toggle('selected', id === viewportId);
  });
  const plane = PLANE_DATA[viewportId];
  const planeLabel = document.getElementById('mpr-slider-plane');
  const topLabel = document.getElementById('mpr-slider-top');
  const bottomLabel = document.getElementById('mpr-slider-bottom');
  if (planeLabel) planeLabel.textContent = plane?.label || 'PLANO';
  if (topLabel) topLabel.textContent = plane?.top || '';
  if (bottomLabel) bottomLabel.textContent = plane?.bottom || '';
  updateMprCounter();
}

function activeViewport() {
  return renderingEngine?.getViewport(activeViewportId);
}

function setTool(tool) {
  if (!Object.hasOwn(TOOL_NAMES, tool) || !toolGroup) return;
  const disabling = activeTool === tool;
  Object.values(TOOL_NAMES).forEach(toolName => {
    try {
      toolGroup.setToolDisabled(toolName);
    } catch (error) {
      console.debug('Herramienta desactivada:', toolName, error);
    }
  });
  if (!disabling) {
    toolGroup.setToolEnabled(TOOL_NAMES[tool]);
    toolGroup.setToolActive(TOOL_NAMES[tool], {
      bindings: [{ mouseButton: ToolsEnums.MouseBindings.Primary }],
    });
    activeTool = tool;
  } else {
    activeTool = null;
  }
  document.querySelectorAll('.tool-button').forEach(button => {
    button.classList.toggle('active-tool', !disabling && button.dataset.tool === tool);
    button.setAttribute('aria-pressed', String(!disabling && button.dataset.tool === tool));
  });
  const labels = {
    pan: 'Mover',
    wl: 'Ventana/nivel',
    zoom: 'Zoom',
    distancia: 'Regla',
    angulo: 'Ángulo',
    roi: 'ROI/HU',
    cruces: 'Cruces enlazadas',
  };
  const result = document.getElementById('measurement-result');
  if (result && active) {
    const instruction = ['distancia', 'angulo', 'roi'].includes(tool)
      ? 'Dibuja la medición con el botón izquierdo sobre cualquier plano.'
      : 'Arrastra con el botón izquierdo sobre el plano deseado.';
    result.textContent = disabling
      ? 'MPR · Herramienta desactivada. Usa la rueda para navegar o selecciona otra herramienta.'
      : `MPR · Herramienta activa: ${labels[tool]}. ${instruction}`;
  }
}

function configureInteractions(viewportId, viewport, element) {
  const select = () => selectViewport(viewportId);
  element.addEventListener('pointerenter', select, true);
  element.addEventListener('pointerdown', select, true);
  element.parentElement?.addEventListener('pointerenter', select, true);
  element.parentElement?.addEventListener('pointerdown', select, true);

  element.addEventListener('wheel', event => {
    event.preventDefault();
    selectViewport(viewportId);
    if (event.ctrlKey) {
      const current = viewport.getZoom();
      viewport.setZoom(Math.max(0.2, Math.min(12, current * (event.deltaY < 0 ? 1.12 : 0.89))));
    } else {
      scrollViewport(viewport, event.deltaY > 0 ? 1 : -1);
    }
    viewport.render();
  }, { passive: false });

  element.addEventListener('dblclick', () => {
    viewport.resetCamera();
    viewport.render();
  });
}

function updateMprCounter(viewport = activeViewport()) {
  if (!viewport) return;
  let index;
  let count;
  try {
    const info = utilities.getVolumeViewportScrollInfo(viewport, volumeId, false);
    index = info.currentStepIndex;
    count = info.numScrollSteps + 1;
  } catch (error) {
    index = viewport.getCurrentImageIdIndex?.();
    count = viewport.getNumberOfSlices?.();
  }
  const counter = document.getElementById('contador-imagen');
  if (counter) {
    counter.textContent = Number.isFinite(index) && Number.isFinite(count)
      ? `MPR · Corte ${index + 1} de ${count}`
      : 'MPR · Plano activo';
  }
  const slider = document.getElementById('slice-slider');
  const mprSlider = document.getElementById('mpr-slice-slider');
  const sliderValue = document.getElementById('slice-slider-value');
  if (Number.isFinite(index) && Number.isFinite(count)) {
    if (slider) {
      slider.max = String(count);
      slider.value = String(index + 1);
    }
    if (sliderValue) sliderValue.textContent = `${index + 1}/${count}`;
    if (mprSlider) {
      mprSlider.max = String(count);
      mprSlider.value = String(index + 1);
    }
  }
}

function scrollViewport(viewport, delta) {
  if (!viewport) return;
  utilities.scroll(viewport, { delta, volumeId, scrollSlabs: true });
  renderingEngine?.renderViewports([viewport.id]);
  window.requestAnimationFrame(() => {
    viewport.render();
    updateMprCounter(viewport);
  });
}

function stopMprCine() {
  mprCinePlaying = false;
  if (mprCineTimer) window.clearTimeout(mprCineTimer);
  mprCineTimer = null;
}

function startMprCine() {
  stopMprCine();
  mprCinePlaying = true;

  const tick = () => {
    if (!mprCinePlaying || !active) return;
    const viewport = activeViewport();
    if (!viewport) return;
    let count;
    let index;
    try {
      const info = utilities.getVolumeViewportScrollInfo(viewport, volumeId, false);
      count = info.numScrollSteps + 1;
      index = info.currentStepIndex;
    } catch (error) {
      count = viewport.getNumberOfSlices?.();
      index = viewport.getCurrentImageIdIndex?.();
    }
    const delta = Number.isFinite(count) && Number.isFinite(index) && index >= count - 1
      ? -(count - 1)
      : 1;
    scrollViewport(viewport, delta);
    const fps = Math.max(1, Number(document.getElementById('cine-velocidad')?.value || 5));
    mprCineTimer = window.setTimeout(() => window.requestAnimationFrame(tick), 1000 / fps);
  };

  tick();
}

function configureToolGroup() {
  [PanTool, WindowLevelTool, ZoomTool, LengthTool, AngleTool, RectangleROITool, CrosshairsTool].forEach(toolClass => {
    try {
      addTool(toolClass);
    } catch (error) {
      if (!String(error).toLowerCase().includes('already')) throw error;
    }
  });

  toolGroup = ToolGroupManager.getToolGroup(toolGroupId)
    || ToolGroupManager.createToolGroup(toolGroupId);
  Object.values(TOOL_NAMES).forEach(toolName => {
    if (toolGroup.hasTool?.(toolName)) return;
    if (toolName === CrosshairsTool.toolName) {
      toolGroup.addTool(toolName, {
        configuration: {
          getReferenceLineColor: viewportId => ({
            LORETO_AXIAL: 'rgb(239,68,68)',
            LORETO_CORONAL: 'rgb(34,197,94)',
            LORETO_SAGITAL: 'rgb(59,130,246)',
          })[viewportId] || 'rgb(34,211,238)',
          getReferenceLineControllable: () => true,
          getReferenceLineDraggableRotatable: () => true,
          getReferenceLineSlabThicknessControlsOn: () => false,
        },
      });
    } else {
      toolGroup.addTool(toolName);
    }
  });
  VIEWPORTS.forEach(([viewportId]) => toolGroup.addViewport(viewportId, renderingEngineId));
  annotation.config.style.setToolGroupToolStyles(toolGroupId, {
    global: {
      color: 'rgb(34,211,238)',
      colorHighlighted: 'rgb(250,204,21)',
      colorSelected: 'rgb(255,255,255)',
      lineWidth: '2',
      textBoxColor: 'rgb(255,255,255)',
      textBoxBackground: 'rgba(0,0,0,0.82)',
      textBoxLinkColor: 'rgb(34,211,238)',
      textBoxShadow: true,
      textBoxFontSize: '14px',
      textBoxFontFamily: 'Arial, sans-serif',
    },
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
    await toolsInit();

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
    renderingEngine = new RenderingEngine(renderingEngineId);
    renderingEngine.setViewports(VIEWPORTS.map(([viewportId, elementId, orientation]) => ({
      viewportId,
      element: document.getElementById(elementId),
      type: Enums.ViewportType.ORTHOGRAPHIC,
      defaultOptions: { orientation, background: [0, 0, 0] },
    })));

    const volume = await volumeLoader.createAndCacheVolume(volumeId, { imageIds });
    await setVolumesForViewports(renderingEngine, [{ volumeId }], VIEWPORTS.map(([id]) => id));
    volume.load();
    configureToolGroup();

    VIEWPORTS.forEach(([id, elementId]) => {
      const viewport = renderingEngine.getViewport(id);
      viewport.resetCamera();
      configureInteractions(id, viewport, document.getElementById(elementId));
    });
    renderingEngine.renderViewports(VIEWPORTS.map(([id]) => id));
    document.getElementById('mpr-loading').hidden = true;
    selectViewport(VIEWPORTS[0][0]);
    setTool('wl');

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
  if (!active) stopMprCine();
  grid.hidden = !active;
  stack.hidden = active;
  button.classList.toggle('active', active);
  button.textContent = active ? 'Vista convencional' : 'MPR 3 planos';
  document.querySelector('.viewer-shell')?.classList.toggle('mpr-active', active);
  if (active) {
    startMpr().then(() => {
      renderingEngine?.resize(true, false);
      renderingEngine?.renderViewports(VIEWPORTS.map(([id]) => id));
    });
  }
}

document.getElementById('activar-mpr')?.addEventListener('click', toggleMpr);
const previousCutBack = document.getElementById('corte-anterior')?.onclick;
const previousCutForward = document.getElementById('corte-siguiente')?.onclick;
const previousCinePlay = document.getElementById('cine-reproducir')?.onclick;
const previousCinePause = document.getElementById('cine-pausar')?.onclick;

document.getElementById('corte-anterior').onclick = event => {
  if (!active) return previousCutBack?.call(event.currentTarget, event);
  stopMprCine();
  scrollViewport(activeViewport(), -1);
};
document.getElementById('corte-siguiente').onclick = event => {
  if (!active) return previousCutForward?.call(event.currentTarget, event);
  stopMprCine();
  scrollViewport(activeViewport(), 1);
};
document.getElementById('cine-pausar').onclick = event => {
  if (!active) return previousCinePause?.call(event.currentTarget, event);
  stopMprCine();
};
document.getElementById('cine-reproducir').onclick = event => {
  if (!active) return previousCinePlay?.call(event.currentTarget, event);
  startMprCine();
};
document.querySelectorAll('.tool-button').forEach(button => {
  button.addEventListener('click', () => {
    if (!active) return;
    setTool(button.dataset.tool);
  });
});
document.getElementById('mpr-slice-slider')?.addEventListener('input', event => {
  if (!active) return;
  stopMprCine();
  const viewport = activeViewport();
  if (!viewport) return;
  try {
    const info = utilities.getVolumeViewportScrollInfo(viewport, volumeId, false);
    const target = Number(event.currentTarget.value) - 1;
    scrollViewport(viewport, target - info.currentStepIndex);
  } catch (error) {
    console.debug('Navegación vertical MPR:', error);
  }
});
document.getElementById('zoom-mas')?.addEventListener('click', () => {
  if (!active) return;
  const viewport = activeViewport();
  viewport.setZoom(Math.min(12, viewport.getZoom() * 1.2));
  viewport.render();
});
document.getElementById('zoom-menos')?.addEventListener('click', () => {
  if (!active) return;
  const viewport = activeViewport();
  viewport.setZoom(Math.max(0.2, viewport.getZoom() / 1.2));
  viewport.render();
});
document.getElementById('restablecer')?.addEventListener('click', () => {
  if (!active) return;
  VIEWPORTS.forEach(([id]) => {
    const viewport = renderingEngine.getViewport(id);
    viewport.resetCamera();
    viewport.resetProperties?.();
    viewport.render();
  });
});
document.getElementById('borrar-mediciones')?.addEventListener('click', () => {
  if (!active) return;
  annotation.state.removeAllAnnotations();
  renderingEngine?.renderViewports(VIEWPORTS.map(([id]) => id));
  const result = document.getElementById('measurement-result');
  if (result) result.textContent = 'MPR · Mediciones eliminadas.';
});
document.getElementById('rotar')?.addEventListener('click', () => {
  if (!active) return;
  const viewport = activeViewport();
  const camera = viewport?.getCamera?.();
  if (!camera?.viewPlaneNormal || !camera?.viewUp) return;
  const [nx, ny, nz] = camera.viewPlaneNormal;
  const [ux, uy, uz] = camera.viewUp;
  const newViewUp = [ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux];
  viewport.setCamera({ viewUp: newViewUp });
  viewport.render();
});
document.getElementById('invertir')?.addEventListener('click', () => {
  if (!active) return;
  const viewport = activeViewport();
  const inverted = !invertedViewports.has(activeViewportId);
  viewport.setProperties({ invert: inverted });
  inverted ? invertedViewports.add(activeViewportId) : invertedViewports.delete(activeViewportId);
  viewport.render();
});
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

