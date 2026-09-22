import { ImageResponse } from "next/og";

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

/** App icon/favicon (docs/07-UI-SPEC.md Polish checklist: "mono F/ glyph in amber"). */
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f59e0b",
          borderRadius: 6,
          color: "#1a1203",
          fontSize: 18,
          fontWeight: 700,
          fontFamily: "monospace",
        }}
      >
        F/
      </div>
    ),
    { ...size }
  );
}
