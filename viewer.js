import * as THREE from 'three';
import { GLTFLoader } from './vendor/loaders/GLTFLoader.js';
import { OrbitControls } from './vendor/controls/OrbitControls.js';

const container = document.querySelector('#threeViewer');
const loading = document.querySelector('#modelLoading');

if (container) {
  const touchDevice = matchMedia('(pointer: coarse)').matches || navigator.maxTouchPoints > 0;
  const normalPixelRatio = Math.min(window.devicePixelRatio, touchDevice ? 0.85 : 1.5);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#07111e');
  scene.fog = new THREE.FogExp2('#07111e', 0.0015);

  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 3000);
  const renderer = new THREE.WebGLRenderer({ antialias: !touchDevice, alpha: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(normalPixelRatio);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !touchDevice;
  controls.dampingFactor = 0.1;
  controls.rotateSpeed = touchDevice ? 1.15 : 0.75;
  controls.zoomSpeed = 0.85;
  controls.autoRotate = false;
  controls.autoRotateSpeed = 1.1;
  controls.enablePan = !touchDevice;
  controls.minDistance = 120;
  controls.maxDistance = 900;

  scene.add(new THREE.HemisphereLight(0xbfe8ff, 0x172033, 2.4));
  const key = new THREE.DirectionalLight(0xffffff, 3.3); key.position.set(250, -350, 450); scene.add(key);
  const rim = new THREE.DirectionalLight(0x67e8f9, 2.0); rim.position.set(-300, 220, 180); scene.add(rim);
  const warm = new THREE.DirectionalLight(0xff9873, 1.2); warm.position.set(250, 280, -100); scene.add(warm);

  const layerMatchers = {
    liver: name => name === 'Liver_Shell',
    lesions: name => name.startsWith('Lesion_'),
    hepatic: name => name === 'Hepatic_Vessels',
    portal: name => name === 'Portal_Vein',
    ivc: name => name === 'Inferior_Vena_Cava',
    aorta: name => name === 'Aorta',
    segments: name => name.startsWith('Segment_'),
    gallbladder: name => name === 'Gallbladder',
    pancreas: name => name === 'Pancreas',
    spleen: name => name === 'Spleen',
    kidneys: name => name.startsWith('Kidney_'),
    duodenum: name => name === 'Duodenum',
  };
  const initial = { liver:true, lesions:true, hepatic:false, portal:false, ivc:false, aorta:false, segments:false, gallbladder:false, pancreas:false, spleen:false, kidneys:false, duodenum:false };
  const layers = Object.fromEntries(Object.keys(layerMatchers).map(key => [key, []]));
  const overlayLayerNames = new Set(Object.keys(layerMatchers).filter(name => !['liver', 'lesions'].includes(name)));
  const lesionLabels = new THREE.Group();
  lesionLabels.name = 'Lesion_Labels';
  scene.add(lesionLabels);
  let rootModel;
  let homeCamera = null;
  let overlaysPromise = null;
  let overlaysReady = false;
  const loader = new GLTFLoader();

  function updateLayerCount() {
    const count = document.querySelectorAll('.layer-toggle.active').length;
    const label = document.querySelector('#visibleLayerCount');
    if (label) label.textContent = `${count} on`;
  }

  function objectLayer(name) {
    return Object.entries(layerMatchers).find(([, match]) => match(name))?.[0];
  }

  function makeLabel(text) {
    const canvas = document.createElement('canvas'); canvas.width = 180; canvas.height = 84;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'rgba(5,15,25,.84)'; ctx.beginPath(); ctx.roundRect(8, 8, 164, 68, 18); ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,.72)'; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = '#fff'; ctx.font = '700 34px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, 90, 43);
    const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map:texture, transparent:true, depthTest:false }));
    sprite.scale.set(18, 8.4, 1); return sprite;
  }

  function exteriorSide(geometry) {
    const position = geometry?.attributes?.position;
    if (!position) return THREE.DoubleSide;
    const index = geometry.index;
    const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), cross = new THREE.Vector3();
    const elementCount = index ? index.count : position.count;
    let signedVolume = 0;
    for (let offset = 0; offset + 2 < elementCount; offset += 3) {
      const ia = index ? index.getX(offset) : offset;
      const ib = index ? index.getX(offset + 1) : offset + 1;
      const ic = index ? index.getX(offset + 2) : offset + 2;
      a.fromBufferAttribute(position, ia);
      b.fromBufferAttribute(position, ib);
      c.fromBufferAttribute(position, ic);
      cross.crossVectors(b, c);
      signedVolume += a.dot(cross);
    }
    return signedVolume < 0 ? THREE.BackSide : THREE.FrontSide;
  }

  function setLayer(name, visible) {
    if (visible && overlayLayerNames.has(name) && !overlaysReady) {
      document.querySelectorAll(`[data-layer="${name}"]`).forEach(button => button.classList.add('loading'));
      ensureOverlays().then(() => setLayer(name, true)).catch(() => {
        document.querySelectorAll(`[data-layer="${name}"]`).forEach(button => button.classList.remove('loading'));
      });
      return;
    }
    (layers[name] || []).forEach(object => object.visible = visible);
    if (name === 'lesions') lesionLabels.visible = visible;
    document.querySelectorAll(`[data-layer="${name}"]`).forEach(button => {
      button.classList.remove('loading');
      button.classList.toggle('active', visible);
      button.setAttribute('aria-pressed', String(visible));
    });
    updateLayerCount();
  }

  function applyPreset(name) {
    const presets = {
      tumor: {liver:true,lesions:true,hepatic:false,portal:false,ivc:false,aorta:false,segments:false,gallbladder:false,pancreas:false,spleen:false,kidneys:false,duodenum:false},
      vascular: {liver:true,lesions:true,hepatic:true,portal:true,ivc:true,aorta:true,segments:false,gallbladder:false,pancreas:false,spleen:false,kidneys:false,duodenum:false},
      context: {liver:false,lesions:true,hepatic:true,portal:true,ivc:true,aorta:true,segments:false,gallbladder:true,pancreas:true,spleen:true,kidneys:true,duodenum:true},
    };
    Object.entries(presets[name]).forEach(([key,value]) => setLayer(key,value));
  }

  function prepareMesh(object, includeLabels = false) {
    if (!object.isMesh) return;
    const layer = objectLayer(object.name);
    if (layer) layers[layer].push(object);
    object.castShadow = false;
    object.receiveShadow = false;
    const outside = exteriorSide(object.geometry);
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    materials.forEach(material => {
      if (layer === 'liver') {
        // A closed liver shell only needs its outward-facing surface. Rendering
        // both transparent sides can resemble a flat cut through the organ.
        material.side = outside;
        material.depthWrite = false;
        material.transparent = true;
        material.needsUpdate = true;
      } else {
        material.side = material.transparent ? THREE.DoubleSide : outside;
        if (material.transparent) material.depthWrite = false;
      }
    });
    if (includeLabels && object.name.startsWith('Lesion_')) {
      const box = new THREE.Box3().setFromObject(object); const center = box.getCenter(new THREE.Vector3());
      const label = makeLabel(object.name.replace('Lesion_','')); label.position.copy(center); label.position.z += 8; lesionLabels.add(label);
    }
  }

  function ensureOverlays() {
    if (overlaysReady) return Promise.resolve();
    if (overlaysPromise) return overlaysPromise;
    overlaysPromise = new Promise((resolve, reject) => {
      loader.load('assets/anatomy_overlays_aug.glb?v=1', gltf => {
        const overlayRoot = gltf.scene;
        overlayRoot.traverse(object => {
          prepareMesh(object);
          if (object.isMesh) object.visible = false;
        });
        scene.add(overlayRoot);
        overlaysReady = true;
        document.querySelectorAll('.layer-toggle.loading').forEach(button => button.classList.remove('loading'));
        resolve();
      }, undefined, error => {
        console.error(error);
        document.querySelectorAll('.layer-toggle.loading').forEach(button => button.classList.remove('loading'));
        overlaysPromise = null;
        reject(error);
      });
    });
    return overlaysPromise;
  }

  loader.load('assets/liver_core_aug.glb?v=1', gltf => {
    rootModel = gltf.scene; scene.add(rootModel);
    rootModel.traverse(object => prepareMesh(object, true));
    Object.entries(initial).forEach(([name,visible]) => setLayer(name,visible));
    const box = new THREE.Box3().setFromObject(rootModel);
    const modelSphere = box.getBoundingSphere(new THREE.Sphere());
    const center = modelSphere.center;
    const verticalFov = THREE.MathUtils.degToRad(camera.fov);
    const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect);
    const limitingFov = Math.max(.1, Math.min(verticalFov, horizontalFov));
    const distance = modelSphere.radius / Math.sin(limitingFov / 2) * 1.08;
    const direction = new THREE.Vector3(.7, -1, .52).normalize();
    controls.target.copy(center); camera.position.copy(center).addScaledVector(direction, distance); camera.lookAt(center);
    camera.near = Math.max(.1, modelSphere.radius / 100);
    camera.far = Math.max(3000, modelSphere.radius * 20);
    camera.updateProjectionMatrix();
    // Never allow the camera to enter the organ, which visually clips it into
    // a cross-section on trackpads and mobile pinch gestures.
    controls.minDistance = modelSphere.radius * 1.35;
    controls.maxDistance = modelSphere.radius * 8;
    controls.update();
    homeCamera = { position:camera.position.clone(), target:center.clone() };
    loading?.remove();
  }, undefined, error => {
    console.error(error);
    const label = loading?.querySelector('span'); if (label) label.textContent = '3D model could not be loaded. Download the GLB below.';
  });

  document.querySelectorAll('.layer-toggle').forEach(button => button.addEventListener('click', () => {
    const name = button.dataset.layer;
    const visible = !button.classList.contains('active');
    if (visible && name === 'segments') setLayer('liver', false);
    if (visible && name === 'liver') setLayer('segments', false);
    setLayer(name, visible);
  }));
  document.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click', () => applyPreset(button.dataset.preset)));
  const anatomyToolbar = document.querySelector('#anatomyToolbar');
  const layerPanelToggle = document.querySelector('#layerPanelToggle');
  layerPanelToggle?.addEventListener('click', () => {
    const open = anatomyToolbar?.classList.toggle('open') ?? false;
    layerPanelToggle.setAttribute('aria-expanded', String(open));
  });
  document.querySelector('#rotateToggle')?.addEventListener('click', event => {
    controls.autoRotate = !controls.autoRotate; event.currentTarget.textContent = controls.autoRotate ? 'Pause rotation' : 'Auto-rotate';
  });
  controls.addEventListener('start', () => {
    if (controls.autoRotate) controls.autoRotate = false;
    const button = document.querySelector('#rotateToggle');
    if (button) button.textContent = 'Auto-rotate';
  });
  document.querySelector('#resetCamera')?.addEventListener('click', () => {
    if (!homeCamera) return; camera.position.copy(homeCamera.position); controls.target.copy(homeCamera.target); controls.update();
  });
  const modelShell = document.querySelector('#modelShell');
  document.querySelector('#fullscreenModel')?.addEventListener('click', () => {
    const request = modelShell?.requestFullscreen || modelShell?.webkitRequestFullscreen;
    request?.call(modelShell);
  });

  function resize() {
    const width = container.clientWidth, height = container.clientHeight;
    renderer.setSize(width,height,false); camera.aspect = width/height; camera.updateProjectionMatrix();
  }
  function resizeAfterFullscreenChange() {
    requestAnimationFrame(() => requestAnimationFrame(resize));
  }
  document.addEventListener('fullscreenchange', resizeAfterFullscreenChange);
  document.addEventListener('webkitfullscreenchange', resizeAfterFullscreenChange);
  new ResizeObserver(resize).observe(container); resize();
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene,camera); });
  window.anatomyViewer = { setLayer, applyPreset };
}
