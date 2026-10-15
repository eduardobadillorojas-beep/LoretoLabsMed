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

const ENGINE_ID = 'LORETO_PUBLIC_ENGINE';
const STACK_ID = 'LORETO_PUBLIC_STACK';
const STACK_GROUP_ID = 'LORETO_PUBLIC_STACK_TOOLS';
const MPR_GROUP_ID = 'LORETO_PUBLIC_MPR_TOOLS';
const MPR_VIEWPORTS = [
  ['LORETO_PUBLIC_AXIAL', 'public-axial', Enums.OrientationAxis.AXIAL],
  ['LORETO_PUBLIC_CORONAL', 'public-coronal', Enums.OrientationAxis.CORONAL],
  ['LORETO_PUBLIC_SAGITAL', 'public-sagital', Enums.OrientationAxis.SAGITTAL],
];
const TOOL_NAMES = {
  pan: PanTool.toolName,
  wl: WindowLevelTool.toolName,
  zoom: ZoomTool.toolName,
  length: LengthTool.toolName,
  angle: AngleTool.toolName,
  roi: RectangleROITool.toolName,
  crosshairs: CrosshairsTool.toolName,
};

let engine;
let manifest;
let activeSeriesIndex = 0;
let mprActive = false;
let mprReadyForSeries = null;
let activeViewportId = STACK_ID;
let activeTool = null;
let volumeId = null;
let stackGroup;
let mprGroup;
let cineTimer = null;
let mprElementsEnabled = false;

const root = document.getElementById('public-dicom-viewer');
const statusElement = document.getElementById('public-status');
const slider = document.getElementById('public-slice-slider');
const counter = document.getElementById('public-counter');
const mprSlider = document.getElementById('public-mpr-slice-slider');
const mprCounter = document.getElementById('public-mpr-counter');

function absoluteUrl(url) {
  return new URL(url, window.location.origin).href;
}

function status(message, error = false) {
  if (!statusElement) return;
  statusElement.textContent = message;
  statusElement.classList.toggle('error', error);
}

function currentSeries() {
  return manifest?.series?.[activeSeriesIndex];
}

function imageIdsForSeries(series) {
  return series.instancias.map(item => `wadouri:${absoluteUrl(item.dicom_url)}`);
}

function activeViewport() {
  return engine?.getViewport(activeViewportId);
}

function allVisibleViewports() {
  return mprActive
    ? MPR_VIEWPORTS.map(([id]) => engine.getViewport(id)).filter(Boolean)
    : [engine.getViewport(STACK_ID)].filter(Boolean);
}

function renderVisible() {
  allVisibleViewports().forEach(viewport => viewport.render());
}

function addTools() {
  [
    PanTool,
    WindowLevelTool,
    ZoomTool,
    LengthTool,
    AngleTool,
    RectangleROITool,
    CrosshairsTool,
  ].forEach(toolClass => {
    try {
      addTool(toolClass);
    } catch (error) {
      if (!String(error).toLowerCase().includes('already')) throw error;
    }
  });
}

function configureGroup(group, includeCrosshairs = false) {
  Object.entries(TOOL_NAMES).forEach(([key, toolName]) => {
    if (key === 'crosshairs' && !includeCrosshairs) return;
    if (group.hasTool?.(toolName)) return;
    if (key === 'crosshairs') {
      group.addTool(toolName, {
        configuration: {
          getReferenceLineColor: viewportId => ({
            LORETO_PUBLIC_AXIAL: 'rgb(239,68,68)',
            LORETO_PUBLIC_CORONAL: 'rgb(34,197,94)',
            LORETO_PUBLIC_SAGITAL: 'rgb(59,130,246)',
          })[viewportId] || 'rgb(34,211,238)',
          getReferenceLineControllable: () => true,
          getReferenceLineDraggableRotatable: () => true,
          getReferenceLineSlabThicknessControlsOn: () => false,
        },
      });
    } else {
      group.addTool(toolName);
    }
  });
}

function applyClinicalStyle(groupId) {
  annotation.config.style.setToolGroupToolStyles(groupId, {
    global: {
      color: 'rgb(34,211,238)',
      colorHighlighted: 'rgb(250,204,21)',
      colorSelected: 'rgb(255,255,255)',
      lineWidth: '2',
      textBoxColor: 'rgb(255,255,255)',
      textBoxBackground: 'rgba(0,0,0,0.86)',
      textBoxLinkColor: 'rgb(34,211,238)',
      textBoxShadow: true,
      textBoxFontSize: '14px',
      textBoxFontFamily: 'Arial, sans-serif',
    },
  });
}

function disableGroupTools(group) {
  if (!group) return;
  Object.values(TOOL_NAMES).forEach(toolName => {
    if (!group.hasTool?.(toolName)) return;
    try {
      group.setToolDisabled(toolName);
    } catch (error) {
      console.debug('No fue posible desactivar', toolName, error);
    }
  });
}

function setTool(tool) {
  if (!Object.hasOwn(TOOL_NAMES, tool)) return;
  if (tool === 'crosshairs' && !mprActive) {
    status('Las cruces se utilizan dentro de MPR 3 planos.');
    return;
  }
  const turnOff = activeTool === tool;
  disableGroupTools(stackGroup);
  disableGroupTools(mprGroup);
  activeTool = turnOff ? null : tool;

  if (!turnOff) {
    const name = TOOL_NAMES[tool];
    [stackGroup, mprGroup].forEach(group => {
      if (!group?.hasTool?.(name)) return;
      group.setToolEnabled(name);
      group.setToolActive(name, {
        bindings: [{ mouseButton: ToolsEnums.MouseBindings.Primary }],
      });
    });
  }

  document.querySelectorAll('[data-public-tool]').forEach(button => {
    const selected = !turnOff && button.dataset.publicTool === tool;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-pressed', String(selected));
  });
  status(turnOff
    ? 'Herramienta desactivada. Usa la rueda o la barra vertical para navegar.'
    : `Herramienta activa: ${document.querySelector(`[data-public-tool="${tool}"]`)?.textContent.trim() || tool}.`);
}

function selectViewport(viewportId) {
  activeViewportId = viewportId;
  document.querySelectorAll('.public-viewport').forEach(element => {
    element.classList.toggle('selected', element.dataset.viewportId === viewportId);
  });
  updateSlider();
}

function scrollActive(delta) {
  const viewport = activeViewport();
  if (!viewport || !delta) return;
  if (mprActive) {
    utilities.scroll(viewport, { delta, volumeId, scrollSlabs: true });
  } else {
    utilities.scroll(viewport, { delta });
  }
  viewport.render();
  window.requestAnimationFrame(updateSlider);
}

function scrollInfo() {
  const viewport = activeViewport();
  if (!viewport) return null;
  if (mprActive) {
    const info = utilities.getVolumeViewportScrollInfo(viewport, volumeId, false);
    return { index: info.currentStepIndex, count: info.numScrollSteps + 1 };
  }
  return {
    index: viewport.getCurrentImageIdIndex?.() ?? 0,
    count: viewport.getNumberOfSlices?.() ?? currentSeries()?.instancias.length ?? 1,
  };
}

function updateSlider() {
  try {
    const info = scrollInfo();
    if (!info || !Number.isFinite(info.index) || !Number.isFinite(info.count)) return;
    [slider, mprSlider].filter(Boolean).forEach(control => {
      control.max = String(Math.max(1, info.count));
      control.value = String(info.index + 1);
    });
    [counter, mprCounter].filter(Boolean).forEach(label => {
      label.textContent = `${info.index + 1}/${info.count}`;
    });
  } catch (error) {
    console.debug('Contador DICOM:', error);
  }
}

function configureViewportInput(element, viewportId) {
  const select = () => selectViewport(viewportId);
  element.addEventListener('pointerenter', select, true);
  element.addEventListener('pointerdown', select, true);
  element.addEventListener('wheel', event => {
    event.preventDefault();
    event.stopPropagation();
    select();
    if (event.ctrlKey) {
      const viewport = activeViewport();
      const next = viewport.getZoom() * (event.deltaY < 0 ? 1.12 : 0.89);
      viewport.setZoom(Math.max(0.2, Math.min(12, next)));
      viewport.render();
    } else {
      scrollActive(event.deltaY > 0 ? 1 : -1);
    }
  }, { passive: false });
  element.addEventListener('dblclick', () => {
    const viewport = engine.getViewport(viewportId);
    viewport.resetCamera();
    viewport.render();
  });
}

async function loadStackSeries(index) {
  stopCine();
  activeSeriesIndex = index;
  mprReadyForSeries = null;
  document.querySelectorAll('[data-series-index]').forEach(button => {
    button.classList.toggle('active', Number(button.dataset.seriesIndex) === index);
  });
  if (mprActive) await toggleMpr(false);
  const viewport = engine.getViewport(STACK_ID);
  await viewport.setStack(imageIdsForSeries(currentSeries()));
  viewport.resetCamera();
  viewport.render();
  selectViewport(STACK_ID);
  document.getElementById('public-mpr-toggle').disabled = !currentSeries().apta_para_volumen;
  status(currentSeries().apta_para_volumen
    ? 'Serie cargada. MPR disponible.'
    : 'Serie cargada. Esta serie no contiene geometría suficiente para MPR.');
}

async function prepareMpr() {
  const series = currentSeries();
  if (!series?.apta_para_volumen) throw new Error('Esta serie no es apta para reconstrucción multiplanar.');
  if (mprReadyForSeries === series.id) return;

  if (!mprElementsEnabled) {
    MPR_VIEWPORTS.forEach(([viewportId, elementId, orientation]) => {
      engine.enableElement({
        viewportId,
        element: document.getElementById(elementId),
        type: Enums.ViewportType.ORTHOGRAPHIC,
        defaultOptions: { orientation, background: [0, 0, 0] },
      });
      mprGroup.addViewport(viewportId, ENGINE_ID);
      configureViewportInput(document.getElementById(elementId), viewportId);
    });
    mprElementsEnabled = true;
  }

  volumeId = `cornerstoneStreamingImageVolume:public-${series.id}`;
  const volume = await volumeLoader.createAndCacheVolume(volumeId, {
    imageIds: imageIdsForSeries(series),
  });
  await setVolumesForViewports(
    engine,
    [{ volumeId }],
    MPR_VIEWPORTS.map(([id]) => id),
  );
  volume.load();
  MPR_VIEWPORTS.forEach(([id]) => engine.getViewport(id).resetCamera());
  mprReadyForSeries = series.id;
}

async function toggleMpr(force) {
  const target = typeof force === 'boolean' ? force : !mprActive;
  if (target === mprActive) return;
  const button = document.getElementById('public-mpr-toggle');
  if (target) {
    status('Preparando reconstrucción multiplanar…');
    document.getElementById('public-stack-stage').hidden = true;
    document.getElementById('public-mpr-grid').hidden = false;
    try {
      await prepareMpr();
      mprActive = true;
      button.textContent = 'Vista axial original';
      button.classList.add('active');
      document.querySelector('[data-public-tool="crosshairs"]').disabled = false;
      engine.resize(true, false);
      engine.renderViewports(MPR_VIEWPORTS.map(([id]) => id));
      selectViewport(MPR_VIEWPORTS[0][0]);
      if (activeTool) {
        const previous = activeTool;
        activeTool = null;
        setTool(previous);
      }
      status('MPR activo. Selecciona un plano y utiliza sus herramientas.');
    } catch (error) {
      document.getElementById('public-stack-stage').hidden = false;
      document.getElementById('public-mpr-grid').hidden = true;
      status(`No fue posible crear MPR: ${error.message}`, true);
    }
  } else {
    mprActive = false;
    document.getElementById('public-stack-stage').hidden = false;
    document.getElementById('public-mpr-grid').hidden = true;
    button.textContent = 'MPR 3 planos';
    button.classList.remove('active');
    document.querySelector('[data-public-tool="crosshairs"]').disabled = true;
    if (activeTool === 'crosshairs') activeTool = null;
    engine.resize(true, false);
    engine.getViewport(STACK_ID).render();
    selectViewport(STACK_ID);
    setTool('pan');
  }
}

function applyPreset(center, width) {
  const range = { lower: center - width / 2, upper: center + width / 2 };
  allVisibleViewports().forEach(viewport => {
    viewport.setProperties({ voiRange: range });
    viewport.render();
  });
}

function stopCine() {
  if (cineTimer) window.clearTimeout(cineTimer);
  cineTimer = null;
}

function startCine() {
  stopCine();
  const tick = () => {
    let info;
    try { info = scrollInfo(); } catch (error) { info = null; }
    if (!info) return;
    scrollActive(info.index >= info.count - 1 ? -(info.count - 1) : 1);
    const fps = Math.max(1, Number(document.getElementById('public-fps').value || 5));
    cineTimer = window.setTimeout(() => requestAnimationFrame(tick), 1000 / fps);
  };
  tick();
}

function bindControls() {
  document.querySelectorAll('[data-public-tool]').forEach(button => {
    button.addEventListener('click', () => setTool(button.dataset.publicTool));
  });
  document.querySelectorAll('[data-window]').forEach(button => {
    button.addEventListener('click', () => {
      const [center, width] = button.dataset.window.split(',').map(Number);
      applyPreset(center, width);
    });
  });
  document.getElementById('public-mpr-toggle').addEventListener('click', () => toggleMpr());
  document.getElementById('public-zoom-plus').addEventListener('click', () => {
    const viewport = activeViewport();
    viewport.setZoom(Math.min(12, viewport.getZoom() * 1.2));
    viewport.render();
  });
  document.getElementById('public-zoom-minus').addEventListener('click', () => {
    const viewport = activeViewport();
    viewport.setZoom(Math.max(0.2, viewport.getZoom() / 1.2));
    viewport.render();
  });
  document.getElementById('public-invert').addEventListener('click', () => {
    const viewport = activeViewport();
    const properties = viewport.getProperties?.() || {};
    viewport.setProperties({ invert: !properties.invert });
    viewport.render();
  });
  document.getElementById('public-rotate').addEventListener('click', () => {
    const viewport = activeViewport();
    const camera = viewport.getCamera?.();
    if (!camera?.viewPlaneNormal || !camera?.viewUp) return;
    const [nx, ny, nz] = camera.viewPlaneNormal;
    const [ux, uy, uz] = camera.viewUp;
    viewport.setCamera({
      viewUp: [ny * uz - nz * uy, nz * ux - nx * uz, nx * uy - ny * ux],
    });
    viewport.render();
  });
  document.getElementById('public-reset').addEventListener('click', () => {
    allVisibleViewports().forEach(viewport => {
      viewport.resetCamera();
      viewport.resetProperties?.();
      viewport.render();
    });
  });
  document.getElementById('public-clear').addEventListener('click', () => {
    annotation.state.removeAllAnnotations();
    renderVisible();
    status('Mediciones eliminadas.');
  });
  document.getElementById('public-prev').addEventListener('click', () => scrollActive(-1));
  document.getElementById('public-next').addEventListener('click', () => scrollActive(1));
  document.getElementById('public-cine').addEventListener('click', startCine);
  document.getElementById('public-pause').addEventListener('click', stopCine);
  [slider, mprSlider].filter(Boolean).forEach(control => {
    control.addEventListener('pointerdown', event => event.stopPropagation());
    control.addEventListener('touchmove', event => {
      event.preventDefault();
      event.stopPropagation();
    }, { passive: false });
    control.addEventListener('input', () => {
      stopCine();
      const target = Number(control.value) - 1;
      const info = scrollInfo();
      scrollActive(target - info.index);
    });
  });
  window.addEventListener('resize', () => {
    engine?.resize(true, false);
    renderVisible();
  });
}

async function start() {
  if (!root) return;
  try {
    status('Preparando visor DICOM…');
    await coreInit();
    await dicomImageLoaderInit({
      maxWebWorkers: Math.max(1, Math.min(4, navigator.hardwareConcurrency || 2)),
    });
    await toolsInit();
    addTools();

    const response = await fetch(root.dataset.manifestUrl, { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`El manifiesto respondió ${response.status}.`);
    manifest = await response.json();
    if (!manifest.series?.length) throw new Error('El estudio no contiene series DICOM disponibles.');

    engine = new RenderingEngine(ENGINE_ID);
    engine.enableElement({
      viewportId: STACK_ID,
      element: document.getElementById('public-stack'),
      type: Enums.ViewportType.STACK,
      defaultOptions: { background: [0, 0, 0] },
    });
    configureViewportInput(document.getElementById('public-stack'), STACK_ID);

    stackGroup = ToolGroupManager.createToolGroup(STACK_GROUP_ID)
      || ToolGroupManager.getToolGroup(STACK_GROUP_ID);
    mprGroup = ToolGroupManager.createToolGroup(MPR_GROUP_ID)
      || ToolGroupManager.getToolGroup(MPR_GROUP_ID);
    configureGroup(stackGroup, false);
    configureGroup(mprGroup, true);
    stackGroup.addViewport(STACK_ID, ENGINE_ID);
    applyClinicalStyle(STACK_GROUP_ID);
    applyClinicalStyle(MPR_GROUP_ID);

    const list = document.getElementById('public-series-list');
    manifest.series.forEach((series, index) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'public-series-card';
      button.dataset.seriesIndex = String(index);
      button.innerHTML = `<strong>${series.modalidad || 'DICOM'}</strong><span>${series.descripcion || 'Serie sin descripción'}</span><small>${series.cantidad_instancias} imágenes${series.apta_para_volumen ? ' · MPR' : ''}</small>`;
      button.addEventListener('click', () => loadStackSeries(index));
      list.appendChild(button);
    });

    bindControls();
    await loadStackSeries(0);
    setTool('pan');
  } catch (error) {
    console.error('Loreto One visor externo:', error);
    status(`No fue posible iniciar el visor: ${error.message}`, true);
  }
}

start();
