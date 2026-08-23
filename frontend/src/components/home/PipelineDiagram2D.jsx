/* ═══════════════════════════════════════════════════════════════
   PipelineDiagram2D — the lightweight stand-in for the WebGL scene.
   ───────────────────────────────────────────────────────────────
   Served when: the viewport is narrow, the user prefers reduced
   motion, or WebGL is unavailable. Hand-built SVG (Tier B) rather
   than a stripped-down screenshot, so it reads as a deliberate
   diagram rather than a broken 3D section.

   The dash animation is the only motion, and it is disabled
   wholesale under prefers-reduced-motion by HomePage.css.
   ═══════════════════════════════════════════════════════════════ */

import React from 'react';

const NODE_X = [46, 138, 230, 322, 414, 506];
const NODE_Y = [64, 96, 58, 100, 66, 92];

export default function PipelineDiagram2D({ activeIndex = null }) {
  const path = NODE_X.map((x, i) => `${i === 0 ? 'M' : 'L'} ${x} ${NODE_Y[i]}`).join(' ');

  return (
    <svg
      className="kp-diagram"
      viewBox="0 0 552 160"
      role="img"
      aria-label="Sơ đồ luồng xử lý: Tài liệu, RAG, LLM, Câu hỏi nháp, Kiểm duyệt, Moodle."
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Base track */}
      <path
        d={path}
        fill="none"
        stroke="var(--h-rule-strong)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Flow overlay — the dash march reads as data moving downstream */}
      <path
        className="kp-diagram-flow"
        d={path}
        fill="none"
        stroke="var(--h-accent)"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray="5 11"
      />
      {NODE_X.map((x, i) => {
        const isActive = activeIndex === i;
        const isLast = i === NODE_X.length - 1;
        return (
          <g key={x}>
            <circle
              cx={x}
              cy={NODE_Y[i]}
              r={isActive ? 15 : 12}
              fill="none"
              stroke={isLast ? 'var(--h-verify)' : 'var(--h-accent)'}
              strokeWidth="1.25"
              opacity={isActive ? 0.95 : 0.4}
            />
            <circle
              cx={x}
              cy={NODE_Y[i]}
              r={isActive ? 6.5 : 5}
              fill={isLast ? 'var(--h-verify)' : 'var(--h-accent)'}
            />
            <text
              x={x}
              y={NODE_Y[i] + (i % 2 === 0 ? -26 : 34)}
              textAnchor="middle"
              className="kp-diagram-num"
            >
              {String(i + 1).padStart(2, '0')}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
