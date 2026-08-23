/* ═══════════════════════════════════════════════════════════════
   KnowledgePipeline3D — the one 3D section on the homepage.
   ───────────────────────────────────────────────────────────────
   Visualises the research pipeline as six connected nodes with
   data-flow particles travelling the edges.

   Deliberate constraints:
   · No decorative floating sphere — every mesh is a pipeline stage
     or an edge between two stages.
   · Labels live in the parent's HTML layer, not in WebGL. Keeps
     text selectable, translatable and screen-reader visible, and
     avoids shipping a font atlas to the GPU.
   · Basic materials + fog only. No lights, no shadow maps, no
     post-processing — the depth cue is fog + z-position + scale.
   · Parallax is capped at ±0.075 rad and damped.
   · The canvas is only mounted by the parent when the section is
     on screen, motion is allowed, and the viewport is wide enough.
   ═══════════════════════════════════════════════════════════════ */

import React, { useMemo, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

/* Mirrors the OKLCH tokens in css/home-tokens.css. WebGL can't read
   CSS custom properties, so this is the single source for scene
   colour — no inline hex anywhere else in the file.
   The section sits on a light field (--h-paper-2), so every colour
   here is tuned to read clearly on white/near-white, not the dark
   field an earlier version of this section used. */
const PALETTE = {
  paper: '#f2f8fc', // fog colour; must match --h-paper-2 in css/home-tokens.css
  node: '#4a7cb0',
  nodeActive: '#0a3d66',
  accent: '#2f8fdd',
  verify: '#1f9c76',
  edge: '#2b5a8c',
  edgeActive: '#1f6bb0',
  particle: '#0d75c7',
};

const NODES = [
  { position: [-6.15, 0.72, -1.25], tone: 'accent' },
  { position: [-3.70, -0.48, 0.35], tone: 'accent' },
  { position: [-1.20, 0.86, 1.10], tone: 'accent' },
  { position: [1.30, -0.40, 0.50], tone: 'accent' },
  { position: [3.80, 0.68, -0.65], tone: 'accent' },
  { position: [6.15, -0.22, -1.60], tone: 'verify' },
];

const PARTICLES_PER_EDGE = 5;
const EDGE_COUNT = NODES.length - 1;
const MAX_TILT = 0.075;

/* ─── One edge, drawn as a thin cylinder between two nodes ────── */
function Edge({ from, to, active }) {
  const { position, quaternion, length } = useMemo(() => {
    const a = new THREE.Vector3(...from);
    const b = new THREE.Vector3(...to);
    const dir = new THREE.Vector3().subVectors(b, a);
    const len = dir.length();
    const q = new THREE.Quaternion().setFromUnitVectors(
      new THREE.Vector3(0, 1, 0),
      dir.clone().normalize(),
    );
    return {
      position: new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5),
      quaternion: q,
      length: len,
    };
  }, [from, to]);

  return (
    <mesh position={position} quaternion={quaternion}>
      <cylinderGeometry args={[0.012, 0.012, length, 6]} />
      <meshBasicMaterial
        color={active ? PALETTE.edgeActive : PALETTE.edge}
        transparent
        /* These opacities were tuned against a dark backdrop, where
           alpha blending darkens toward black and reads as *more*
           saturated. On the light --h-paper-2 field the same alpha
           blends toward white and washes out — 0.55 measured only
           2.5:1 against the page background. 0.85 clears 3:1. */
        opacity={active ? 0.95 : 0.85}
      />
    </mesh>
  );
}

/* ─── One pipeline stage: inner core + orbit ring ─────────────── */
function Node({ position, tone, active }) {
  const ring = useRef();

  useFrame((_, delta) => {
    if (!ring.current) return;
    const target = active ? 1.22 : 1;
    // Damped scale — no spring, no overshoot.
    const next = THREE.MathUtils.damp(ring.current.scale.x, target, 6, delta);
    ring.current.scale.setScalar(next);
    ring.current.rotation.z += delta * (active ? 0.32 : 0.12);
  });

  const core = tone === 'verify' ? PALETTE.verify : PALETTE.accent;

  return (
    <group position={position}>
      <mesh>
        <sphereGeometry args={[0.3, 20, 16]} />
        <meshBasicMaterial color={active ? PALETTE.nodeActive : core} />
      </mesh>
      <mesh ref={ring} rotation={[Math.PI / 2.6, 0, 0]}>
        <torusGeometry args={[0.56, 0.018, 8, 44]} />
        <meshBasicMaterial
          color={active ? PALETTE.nodeActive : PALETTE.node}
          transparent
          /* Same light-backdrop correction as the edge material —
             0.42 measured only 1.68:1 on --h-paper-2. */
          opacity={active ? 0.92 : 0.85}
        />
      </mesh>
    </group>
  );
}

/* ─── Data-flow particles, one buffer for the whole pipeline ──── */
function FlowParticles({ activeIndex }) {
  const points = useRef();
  const total = EDGE_COUNT * PARTICLES_PER_EDGE;

  const { positions, offsets, edges } = useMemo(() => {
    const pos = new Float32Array(total * 3);
    const off = new Float32Array(total);
    const segs = [];
    for (let e = 0; e < EDGE_COUNT; e += 1) {
      segs.push({
        a: new THREE.Vector3(...NODES[e].position),
        b: new THREE.Vector3(...NODES[e + 1].position),
      });
      for (let p = 0; p < PARTICLES_PER_EDGE; p += 1) {
        off[e * PARTICLES_PER_EDGE + p] = p / PARTICLES_PER_EDGE;
      }
    }
    return { positions: pos, offsets: off, edges: segs };
  }, [total]);

  useFrame((state) => {
    if (!points.current) return;
    const t = state.clock.elapsedTime * 0.19;
    const arr = points.current.geometry.attributes.position.array;
    for (let e = 0; e < EDGE_COUNT; e += 1) {
      const { a, b } = edges[e];
      for (let p = 0; p < PARTICLES_PER_EDGE; p += 1) {
        const i = e * PARTICLES_PER_EDGE + p;
        const k = (t + offsets[i]) % 1;
        arr[i * 3] = a.x + (b.x - a.x) * k;
        arr[i * 3 + 1] = a.y + (b.y - a.y) * k;
        arr[i * 3 + 2] = a.z + (b.z - a.z) * k;
      }
    }
    points.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={points}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          count={total}
          array={positions}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.11}
        color={PALETTE.particle}
        transparent
        /* 0.72 measured 2.84:1 on the light field — under 0.9 it
           blends too close to --h-paper-2 to read as a moving dot. */
        opacity={activeIndex === null ? 0.9 : 1}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}

/* ─── Scene root: fits the arc to the viewport, damps parallax ── */
function Scene({ activeIndex }) {
  const group = useRef();
  const { viewport } = useThree();

  // Fit the 12.3-unit-wide arc into the available width, capped so
  // it never balloons on ultra-wide displays.
  const fit = Math.min(1, viewport.width / 14.6);

  useFrame((state, delta) => {
    if (!group.current) return;
    const { x, y } = state.pointer; // −1 … 1, already normalised
    const targetY = x * MAX_TILT;
    const targetX = -y * MAX_TILT * 0.6;
    group.current.rotation.y = THREE.MathUtils.damp(group.current.rotation.y, targetY, 3.4, delta);
    group.current.rotation.x = THREE.MathUtils.damp(group.current.rotation.x, targetX, 3.4, delta);
  });

  return (
    <group ref={group} scale={fit}>
      {NODES.slice(0, -1).map((node, i) => (
        <Edge
          key={`edge-${i}`}
          from={node.position}
          to={NODES[i + 1].position}
          active={activeIndex === i || activeIndex === i + 1}
        />
      ))}
      <FlowParticles activeIndex={activeIndex} />
      {NODES.map((node, i) => (
        <Node
          key={`node-${i}`}
          position={node.position}
          tone={node.tone}
          active={activeIndex === i}
        />
      ))}
    </group>
  );
}

export default function KnowledgePipeline3D({ activeIndex = null, paused = false, onReady }) {
  return (
    <Canvas
      className="kp-canvas"
      /* Fires only once the R3F root has configured against a real
         size — the parent uses it to stop its re-measure retry. */
      onCreated={onReady}
      dpr={[1, 1.75]}
      /* 'demand' rather than 'never' when paused: it still stops the
         continuous rAF loop (so an off-screen section costs no GPU
         time), but leaves R3F able to size the drawing buffer and
         respond to resize. 'never' suppresses those too, which
         leaves the canvas stuck at its 300x150 default. */
      frameloop={paused ? 'demand' : 'always'}
      /* The app mounts under React.StrictMode (src/main.jsx). Its
         double-invoked effects make react-use-measure — which R3F
         uses internally — drop the first measurement, so the canvas
         would otherwise stay at 300x150 forever. Measuring without
         the debounce, and without scroll tracking we don't need,
         makes the initial size land reliably. */
      resize={{ debounce: 0, scroll: false }}
      camera={{ position: [0, 0, 9], fov: 45 }}
      gl={{ antialias: true, powerPreference: 'low-power', alpha: true }}
      /* Decorative: the HTML stage list below carries the real content. */
      aria-hidden="true"
      tabIndex={-1}
    >
      <fog attach="fog" args={[PALETTE.paper, 9, 19]} />
      <Scene activeIndex={activeIndex} />
    </Canvas>
  );
}
