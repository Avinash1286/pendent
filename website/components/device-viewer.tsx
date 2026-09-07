import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

type Props = {
  mode: 'hero' | 'configure';
  finish: string;
  exploded?: boolean;
  resetKey?: number;
};
export default function DeviceViewer({
  mode,
  finish,
  exploded = false,
  resetKey = 0,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const state = useRef<{
    model: THREE.Group;
    controls: OrbitControls;
    camera: THREE.PerspectiveCamera;
    paint: THREE.MeshStandardMaterial[];
    bases: Map<THREE.Object3D, THREE.Vector3>;
    size: number;
  } | null>(null);
  const options = useRef({ finish, exploded });
  useEffect(() => {
    options.current = { finish, exploded };
  }, [finish, exploded]);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const host = container.current;
    if (!host) return;
    let disposed = false,
      frame = 0,
      visible = true;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: 'low-power',
      });
    } catch {
      queueMicrotask(() => setFailed(true));
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.setClearColor(0, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = mode === 'hero' ? 1.3 : 1.45;
    host.appendChild(renderer.domElement);
    renderer.domElement.setAttribute(
      'aria-label',
      'Interactive AURA pendant. Drag to rotate.',
    );
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 100);
    camera.position.set(0.15, 0.12, 4.2);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.autoRotate = !window.matchMedia('(prefers-reduced-motion: reduce)')
      .matches;
    controls.autoRotateSpeed = 0.35;
    controls.minPolarAngle = Math.PI * 0.2;
    controls.maxPolarAngle = Math.PI * 0.8;
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const environment = pmrem.fromScene(room, 0.06);
    scene.environment = environment.texture;
    room.dispose();
    pmrem.dispose();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x54545d, 2));
    const key = new THREE.DirectionalLight(0xffffff, 3.2);
    key.position.set(-2, 3, 4);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xf5d1b8, 2);
    rim.position.set(3, 1, -2);
    scene.add(rim);
    const resize = () => {
      if (!host.clientWidth || !host.clientHeight) return;
      renderer.setSize(host.clientWidth, host.clientHeight);
      camera.aspect = host.clientWidth / host.clientHeight;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();
    const intersection = new IntersectionObserver(
      (entries) => {
        visible = entries[0]?.isIntersecting ?? true;
      },
      { rootMargin: '100px' },
    );
    intersection.observe(host);
    const onContextLost = (event: Event) => {
      event.preventDefault();
      setFailed(true);
      setReady(false);
    };
    renderer.domElement.addEventListener('webglcontextlost', onContextLost);
    const stopAuto = () => {
      controls.autoRotate = false;
    };
    controls.addEventListener('start', stopAuto);
    new GLTFLoader().load(
      '/product/aura.glb',
      (gltf) => {
        if (disposed) {
          gltf.scene.traverse((o) => {
            if (o instanceof THREE.Mesh) {
              o.geometry.dispose();
              const mats = Array.isArray(o.material)
                ? o.material
                : [o.material];
              mats.forEach((m) => m.dispose());
            }
          });
          return;
        }
        const model = gltf.scene;
        model.rotation.x = Math.PI / 2;
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        const scale = 2.15 / Math.max(size.x, size.y, size.z);
        model.scale.multiplyScalar(scale);
        model.position.sub(center.multiplyScalar(scale));
        const pivot = new THREE.Group();
        pivot.add(model);
        scene.add(pivot);
        pivot.rotation.set(
          -0.07,
          mode === 'hero' ? -0.3 : -0.18,
          mode === 'hero' ? -0.15 : 0.04,
        );
        const paint: THREE.MeshStandardMaterial[] = [];
        const bases = new Map<THREE.Object3D, THREE.Vector3>();
        model.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            const materials = Array.isArray(object.material)
              ? object.material
              : [object.material];
            materials.forEach((material: THREE.Material) => {
              if (
                material instanceof THREE.MeshStandardMaterial &&
                /shell|housing|ceramic|satin|body|titanium|lunar/i.test(
                  material.name + ' ' + object.name,
                ) &&
                !/battery|pcb|cord|gasket|button|black/i.test(object.name)
              ) {
                material.color.set(options.current.finish);
                material.metalness = 0.32;
                material.roughness = 0.34;
                paint.push(material);
              }
            });
          }
        });
        model.children.forEach((object) =>
          bases.set(object, object.position.clone()),
        );
        state.current = {
          model: pivot,
          controls,
          camera,
          paint,
          bases,
          size: Math.max(size.x, size.y, size.z),
        };
        setReady(true);
      },
      undefined,
      () => {
        if (!disposed) setFailed(true);
      },
    );
    let last = 0;
    const animate = (time: number) => {
      frame = requestAnimationFrame(animate);
      if (!visible || document.hidden || time - last < 30) return;
      last = time;
      const live = state.current;
      if (live) {
        live.bases.forEach((base, object) => {
          const n = object.name.toLowerCase();
          let distance = 0;
          if (options.current.exploded) {
            if (/front|button|led|acoustic|record_plunger/.test(n))
              distance = live.size * 0.35;
            else if (/rear|back|pogo|charging|case_screw/.test(n))
              distance = -live.size * 0.35;
            else if (/battery/.test(n)) distance = -live.size * 0.16;
          }
          object.position.y = THREE.MathUtils.lerp(
            object.position.y,
            base.y + distance,
            0.065,
          );
        });
      }
      controls.update();
      renderer.render(scene, camera);
    };
    frame = requestAnimationFrame(animate);
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      intersection.disconnect();
      controls.dispose();
      environment.dispose();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh) {
          o.geometry.dispose();
          const materials = Array.isArray(o.material)
            ? o.material
            : [o.material];
          materials.forEach((m) => m.dispose());
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      state.current = null;
    };
  }, [mode]);
  useEffect(() => {
    state.current?.paint.forEach((m) => m.color.set(finish));
  }, [finish]);
  useEffect(() => {
    const live = state.current;
    if (live && mode === 'configure') {
      live.model.rotation.y = exploded ? -0.85 : -0.18;
      live.camera.position.set(0.15, 0.12, exploded ? 5.0 : 4.2);
      live.controls.autoRotate = false;
      live.controls.update();
    }
  }, [exploded, mode]);
  useEffect(() => {
    const live = state.current;
    if (live) {
      live.camera.position.set(0.15, 0.12, 4.2);
      live.model.rotation.set(
        -0.07,
        mode === 'hero' ? -0.3 : -0.18,
        mode === 'hero' ? -0.15 : 0.04,
      );
      live.controls.target.set(0, 0, 0);
      live.controls.update();
    }
  }, [resetKey, mode]);
  return (
    <div className="device-view">
      <img
        className={`device-fallback ${ready ? 'loaded' : ''}`}
        src="/product/transparent.webp"
        alt="AURA pendant with a soft satin shell, record button and woven necklace cord"
        loading={mode === 'hero' ? 'eager' : 'lazy'}
      />
      <div ref={container} className="device-canvas" />
      <button
        className="device-keyboard"
        onClick={() => {
          const live = state.current;
          if (live) live.model.rotation.y += Math.PI / 4;
        }}
      >
        Rotate the AURA model
      </button>
      {!ready && !failed && (
        <span className="viewer-loading">Preparing your view…</span>
      )}
      {failed && (
        <span className="viewer-loading">
          Product image · 3D is unavailable on this device
        </span>
      )}
    </div>
  );
}
