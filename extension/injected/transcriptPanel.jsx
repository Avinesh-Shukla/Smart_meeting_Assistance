import React from "react";

export default function TranscriptPanel({ lines }) {
  return (
    <section className="sma-card">
      <h3>Live Transcript</h3>
      <div className="sma-scroll-area">
        {lines.length === 0 && <p className="sma-empty">Waiting for transcript...</p>}
        {lines.map((line, index) => (
          <p key={`${line}-${index}`} className="sma-line">
            {line}
          </p>
        ))}
      </div>
    </section>
  );
}
